"""TimePay (timepay24.uz) -> our HR DB. READ-ONLY on the TimePay side.
Syncs branches, departments, positions, employees (with assigned salary) and Face ID / QR / GPS check-ins.
Idempotent through external_refs. Auth: TIMEPAY_TOKEN (Bearer). API: https://api.app.time-pay.uz/api/v1/integration

python -m app.importers.timepay --days 35      # first run / backfill
python -m app.importers.timepay --days 2       # frequent refresh"""
from __future__ import annotations

import argparse
import os
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import cfg
from ..db import SessionLocal, init_db
from ..models import AttendanceEvent, Branch, Department, Employee, ExternalRef, Position
from ..rbac import audit

BASE = "https://api.app.time-pay.uz/api/v1/integration"
SRC = "timepay"
TZ = ZoneInfo(cfg("company.timezone", "Asia/Tashkent"))
VERIFIED = {"FACE_ID": "face", "QR": "qr", "GPS": "geo"}


class TimePayError(Exception):
    pass


def _get(client: httpx.Client, path: str, params: dict | None = None) -> dict:
    for attempt in range(4):
        r = client.get(path if path.startswith("http") else f"{BASE}/{path.lstrip('/')}", params=params)
        if r.status_code == 429:
            time.sleep(min(int(r.headers.get("Retry-After") or 5), 30))
            continue
        if r.status_code >= 400:
            try:
                code = r.json().get("error_code")
            except ValueError:
                code = None
            raise TimePayError(f"HTTP {r.status_code} {code or ''}".strip())
        return r.json()
    raise TimePayError("rate limited")


def _all(client: httpx.Client, path: str, params: dict | None = None) -> list[dict]:
    out, url, p = [], path, {**(params or {}), "limit": 100}
    while url and len(out) < 20000:
        j = _get(client, url, p)
        out += j.get("results", []) if isinstance(j, dict) else []
        url, p = (j or {}).get("next"), None
    return out


def _ref(db: Session, kind: str, ext) -> ExternalRef | None:
    return db.scalar(select(ExternalRef).where(ExternalRef.source == SRC, ExternalRef.kind == kind,
                                               ExternalRef.external_id == str(ext)))


def _link(db: Session, kind: str, ext, local_id: int) -> None:
    db.add(ExternalRef(source=SRC, kind=kind, external_id=str(ext), local_id=local_id))


def _dict_item(db: Session, kind: str, ext_id, name: str, make) -> int:
    r = _ref(db, kind, ext_id)
    if r:
        return r.local_id
    obj = make(name)
    db.add(obj)
    db.flush()
    _link(db, kind, ext_id, obj.id)
    return obj.id


def _name(e: dict) -> str:
    return " ".join(x for x in (e.get("first_name"), e.get("last_name")) if x).strip() or f"TimePay #{e.get('id')}"


def _local(ts: str) -> datetime:
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return (d.astimezone(TZ) if d.tzinfo else d).replace(tzinfo=None)


def _hm(v) -> int:
    h, m = str(v or "00:00")[:5].split(":")
    return int(h) * 60 + int(m)


def schedule_code(s: dict) -> str | None:
    """TimePay schedule -> one of our schedule codes (config `schedules`) with the same start, hours and weekdays."""
    days = [d for d in s.get("work_days") or [] if d.get("is_working")]
    if not days:
        return None
    d0 = days[0]
    lunch = (_hm(d0.get("break_end")) - _hm(d0.get("break_start"))) if d0.get("break_start") else 0
    spec = {"start": str(d0.get("start_time"))[:5], "hours": (_hm(d0.get("end_time")) - _hm(d0.get("start_time")) - lunch) / 60,
            "weekdays": sorted(int(d["day"]) - 1 for d in days)}  # TimePay 1=Mon -> ours 0=Mon
    for code, ours in (cfg("schedules", {}) or {}).items():
        if ours.get("type") == "fixed" and ours.get("start") == spec["start"] and float(ours.get("hours")) == spec["hours"] \
                and sorted(ours.get("weekdays", [])) == spec["weekdays"]:
            return code
    return None


def _money_month(db: Session, client: httpx.Client, emp_map: dict[int, int], year: int, month: int, stats: dict) -> None:
    """Fines -> penalty, bonuses -> bonus, deductions -> other. Never touches an approved/closed month."""
    from ..models import PayrollEntry
    from ..services import payroll
    mon = f"{year}-{month:02d}"
    if payroll.is_locked(db, mon):
        return
    feeds = [("fines/", "fine", "penalty"), ("bonuses/", "bonus", "bonus"), ("deductions/", "deduction", "other")]
    for path, kind, entry_kind in feeds:
        try:
            items = _all(client, path, {"year": year, "month": month})
        except TimePayError:
            continue  # token without this permission
        for x in items:
            eid = emp_map.get((x.get("employee") or {}).get("id"))
            if not eid or _ref(db, kind, x["id"]):
                continue
            amount = float(x.get("amount") or 0)
            if kind == "fine" and str(x.get("amount_type") or "AMOUNT").upper() != "AMOUNT":
                base = db.get(Employee, eid).base_salary
                if not base:
                    continue  # percent fine without a known salary: leave it to a person
                amount = base * amount / 100
            if amount <= 0:
                continue
            label = {"fine": "Jarima", "bonus": "Bonus", "deduction": "Ushlab qolish"}[kind]
            detail = x.get("reason") or x.get("description") or x.get("fine_type") or x.get("type") or ""
            if kind == "deduction" and x.get("is_unpaid_leave"):
                detail = f"to'lanmagan ta'til · {detail}".strip(" ·")
            e = PayrollEntry(employee_id=eid, month=mon, kind=entry_kind, amount=round(amount), author=SRC,
                             reason=f"TimePay {label}: {detail}"[:300] if detail else f"TimePay {label}")
            db.add(e)
            db.flush()
            _link(db, kind, x["id"], e.id)
            payroll.mark_changed(db, mon)
            stats["money_new"] += 1


def sync(days: int = 2, token: str | None = None, transport: httpx.BaseTransport | None = None) -> dict:
    token = token or os.getenv("TIMEPAY_TOKEN", "")
    if not token:
        raise TimePayError("TIMEPAY_TOKEN is not set")
    init_db()
    stats = {"employees_new": 0, "employees_updated": 0, "checkins_new": 0, "money_new": 0, "days": days}
    with httpx.Client(timeout=40, headers={"Authorization": f"Bearer {token}"}, transport=transport) as client, \
            SessionLocal() as db:
        # dictionaries
        branches = {b["id"]: _dict_item(db, "branch", b["id"], b["name"], lambda n, b=b: Branch(
            code=f"TP{b['id']}"[:20], name=n, mode="day", city=None)) for b in _all(client, "branches/")}
        depts = {}
        for d in _all(client, "departments/"):
            existing = db.scalar(select(Department).where(Department.name == d["name"]))
            if existing and not _ref(db, "department", d["id"]):
                _link(db, "department", d["id"], existing.id)
            depts[d["id"]] = _dict_item(db, "department", d["id"], d["name"], lambda n: Department(name=n, description="TimePay"))
        positions = {p["id"]: _dict_item(db, "position", p["id"], p["name"], lambda n, p=p: Position(
            code=f"tp_{p['id']}", title=n)) for p in _all(client, "positions/")}
        main_branch = next(iter(branches.values()), None)

        # salaries of the current month (assigned salary -> base_salary)
        today = datetime.now(TZ).date()
        salary = {}
        try:
            for s in _all(client, "salary/monthly/", {"year": today.year, "month": today.month}):
                if s.get("assigned_salary") is not None:
                    salary[s["employee_id"]] = (int(float(s["assigned_salary"])), str(s.get("salary_type") or "").lower())
        except TimePayError:
            pass  # token without read_salary: salaries stay unknown ("—")

        # work schedules: TimePay schedule -> our schedule code per employee
        sched_of: dict[int, str] = {}
        try:
            for s in _all(client, "schedules/"):
                code = schedule_code(s)
                for eid in s.get("employee_ids") or []:
                    if code:
                        sched_of[eid] = code
        except TimePayError:
            pass

        # employees
        emp_map: dict[int, int] = {}
        for e in _all(client, "employees/"):
            fields = {"full_name": _name(e)[:160], "phone": (e.get("phone_number") or None),
                      "department_id": depts.get((e.get("department") or {}).get("id")),
                      "position_id": positions.get((e.get("position") or {}).get("id")),
                      "branch_id": branches.get(((e.get("branches") or [{}])[0] or {}).get("id")) or main_branch}
            if e.get("work_start_date"):
                fields["hire_date"] = date.fromisoformat(e["work_start_date"][:10])
            if e.get("resigned_at") or not e.get("is_active", True):
                fields["status"], fields["fire_date"] = "fired", date.fromisoformat((e.get("resigned_at") or today.isoformat())[:10])
            fields["schedule_code"] = sched_of.get(e["id"]) or cfg("imports.timepay.schedule_code", "day_9_18")
            if e["id"] in salary:
                amount, kind = salary[e["id"]]
                fields["base_salary"] = amount
                fields["pay_type"] = "hourly" if "hour" in kind else "daily" if "day" in kind else "monthly"
            r = _ref(db, "employee", e["id"])
            if r and (emp := db.get(Employee, r.local_id)):
                changed = any(getattr(emp, k) != v for k, v in fields.items())
                for k, v in fields.items():
                    setattr(emp, k, v)
                stats["employees_updated"] += int(changed)
            else:
                emp = Employee(status="active", **fields)
                db.add(emp)
                db.flush()
                _link(db, "employee", e["id"], emp.id)
                stats["employees_new"] += 1
                if emp.hire_date and emp.hire_date >= today - timedelta(days=30):  # newly hired -> onboarding course
                    from ..services import onboarding_media
                    from ..rbac import Scope
                    onboarding_media.auto_assign(db, Scope("system:timepay", "owner", None, False), emp)
            emp_map[e["id"]] = emp.id

        # check-ins, day by day (the API has no company-wide month mode)
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            for x in _all(client, "checkinouts/", {"date": d.isoformat()}):
                if str(x.get("status") or "").upper() in ("REJECTED", "FAILED") or x.get("action") not in ("IN", "OUT"):
                    continue
                eid = emp_map.get((x.get("employee") or {}).get("id"))
                if not eid or _ref(db, "checkin", x["id"]):
                    continue
                ev = AttendanceEvent(employee_id=eid, kind=x["action"].lower(), ts=_local(x["created_at"]), source=SRC,
                                     verified=VERIFIED.get(str(x.get("source")), "none"))
                db.add(ev)
                db.flush()
                _link(db, "checkin", x["id"], ev.id)
                stats["checkins_new"] += 1
        # money: this month and the previous one (late corrections)
        prev = (today.replace(day=1) - timedelta(days=1))
        for y, m in ((prev.year, prev.month), (today.year, today.month)):
            _money_month(db, client, emp_map, y, m, stats)
        audit(db, None, "import_timepay", None, **stats)
        db.commit()
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=2)
    print(sync(min(max(ap.parse_args().days, 1), 62)))
