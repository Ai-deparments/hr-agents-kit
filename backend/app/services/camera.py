"""AI camera -> attendance. Vendor-neutral webhook: the camera service signs every delivery with
X-Signature: sha256=HMAC(secret, "<X-Timestamp>.<raw body>"). Rules:
- a delivery id is processed once (retries are answered 200 'duplicate');
- a name is matched to exactly one active employee (normalised full name) — unmatched / ambiguous are stored, never guessed;
- arrival keeps the earliest camera time of the day, leave keeps the latest;
- human marks (Mini App, team lead, HR edit) always win over camera marks (see attendance.compute_day);
- photos are never stored: image / base64 fields are stripped before anything is saved."""
from __future__ import annotations

import hashlib
import hmac
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import cfg, settings
from ..models import AttendanceEvent, Branch, CameraDelivery, CameraEvent, CameraVisit, Employee
from ..rbac import Scope
from . import payroll
from . import schedules as sch
from .people import norm_name

EVENTS = {"staff.arrived", "staff.left", "visits.hour", "timesheet.day", "test"}
_IMAGE_KEYS = re.compile(r"photo|image|img|snapshot|picture|face|frame|base64|thumb", re.I)
_B64 = re.compile(r"^[A-Za-z0-9+/=\r\n]{200,}$")


class BadEvent(ValueError):
    pass


# ---------------- signature ----------------

def verify_signature(secret: str, timestamp: str | None, signature: str | None, raw: bytes, now: float) -> str | None:
    """Returns None when valid, otherwise a short reason (never echoes the secret or the expected value)."""
    if not timestamp or not signature:
        return "missing signature headers"
    try:
        ts = int(timestamp)
    except ValueError:
        return "bad timestamp"
    if abs(now - ts) > int(cfg("camera.timestamp_window_s", 300)):
        return "timestamp outside the allowed window"
    if not signature.startswith("sha256="):
        return "bad signature format"
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature[7:].strip().lower(), expected):
        return "bad signature"
    return None


def strip_images(obj):
    """Drop photo / base64 fields at any depth. Nothing image-like reaches the database or the logs."""
    if isinstance(obj, dict):
        return {k: strip_images(v) for k, v in obj.items()
                if not (_IMAGE_KEYS.search(str(k)) or (isinstance(v, str) and _looks_like_image(v)))}
    if isinstance(obj, list):
        return [strip_images(v) for v in obj if not (isinstance(v, str) and _looks_like_image(v))]
    return obj


def _looks_like_image(s: str) -> bool:
    return s.startswith("data:image") or bool(_B64.match(s[:4096]))


# ---------------- helpers ----------------

def _tz():
    try:
        return ZoneInfo(cfg("company.timezone", "Asia/Tashkent"))
    except Exception:  # unknown zone name: keep the camera's wall clock
        return None


def parse_time(v) -> datetime:
    """ISO time from the camera -> naive company-local time (the kit stores local wall-clock times)."""
    if not isinstance(v, str) or not v:
        raise BadEvent("time is required")
    try:
        t = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        raise BadEvent("time must be ISO 8601")
    if t.tzinfo is not None:
        tz = _tz()
        t = t.astimezone(tz).replace(tzinfo=None) if tz else t.replace(tzinfo=None)
    return t


def _name_key(s: str) -> str:
    return " ".join(sorted(norm_name(s or "").split()))


def _name_index(db: Session, branch_code: str | None, cache: dict) -> dict[str, list[int]]:
    """Normalised name -> employee ids, built once per delivery (a timesheet may carry thousands of rows)."""
    ck = branch_code if branch_code and cfg("camera.match_by_branch", True) else None
    if ck not in cache:
        q = select(Employee).where(Employee.status != "fired")
        if ck:
            b = db.scalar(select(Branch).where(Branch.code == ck))
            if b:
                q = q.where(Employee.branch_id == b.id)
        idx: dict[str, list[int]] = defaultdict(list)
        for e in db.scalars(q):
            idx[_name_key(e.full_name)].append(e.id)
        cache[ck] = idx
    return cache[ck]


def match_employee(db: Session, raw_name: str, branch_code: str | None, cache: dict | None = None) -> tuple[str, int | None]:
    key = _name_key(raw_name)
    if not key:
        return "unmatched", None
    hits = _name_index(db, branch_code, {} if cache is None else cache).get(key, [])
    if len(hits) == 1:
        return "matched", hits[0]
    return ("ambiguous" if hits else "unmatched"), None


def _apply_mark(db: Session, emp_id: int, kind: str, ts: datetime) -> tuple[bool, str | None]:
    """Earliest arrival / latest leave per day; one camera mark per kind per day."""
    if payroll.is_locked(db, ts.strftime("%Y-%m")):
        return False, "month is closed"
    att_kind = "in" if kind == "arrived" else "out"
    t0 = datetime.combine(ts.date(), datetime.min.time())
    cur = db.scalar(select(AttendanceEvent).where(AttendanceEvent.employee_id == emp_id, AttendanceEvent.kind == att_kind,
                                                  AttendanceEvent.source == "camera", AttendanceEvent.ts >= t0,
                                                  AttendanceEvent.ts < t0 + timedelta(days=1)))
    if cur is None:
        db.add(AttendanceEvent(employee_id=emp_id, kind=att_kind, ts=ts, source="camera", verified="camera"))
        payroll.mark_changed(db, ts.strftime("%Y-%m"))
        return True, None
    if (att_kind == "in" and ts < cur.ts) or (att_kind == "out" and ts > cur.ts):
        cur.ts = ts
        payroll.mark_changed(db, ts.strftime("%Y-%m"))
        return True, None
    return False, "earlier arrival / later leave already recorded"


def _person(db: Session, delivery_id: str, kind: str, raw_name, when, branch_code, cache: dict | None = None) -> dict:
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise BadEvent("full_name is required")
    ts = parse_time(when)
    name = raw_name.strip()[:160]
    code = str(branch_code)[:20] if branch_code else None
    match, emp_id = match_employee(db, name, code, cache)
    applied, note = (_apply_mark(db, emp_id, kind, ts) if emp_id else (False, None))
    db.add(CameraEvent(delivery_id=delivery_id, kind=kind, ts=ts, day=ts.date(), raw_name=name, branch_code=code,
                       match=match, employee_id=emp_id, applied=applied, note=note))
    return {"kind": kind, "match": match, "applied": applied}


# ---------------- entry point ----------------

def handle(db: Session, delivery_id: str, payload: dict) -> dict:
    """Process one verified delivery. Caller commits. Raises BadEvent on a malformed payload."""
    if not isinstance(payload, dict):
        raise BadEvent("body must be a JSON object")
    event = payload.get("event")
    if event not in EVENTS:
        raise BadEvent("unknown event")
    if not delivery_id or len(delivery_id) > 80:
        raise BadEvent("delivery id is required (max 80 chars)")
    if db.scalar(select(CameraDelivery.id).where(CameraDelivery.delivery_id == delivery_id)):
        return {"ok": True, "duplicate": True}
    clean = strip_images(payload)
    data = clean.get("data") or {}
    if not isinstance(data, dict):
        raise BadEvent("data must be an object")
    db.add(CameraDelivery(delivery_id=delivery_id, event=event, payload=clean))
    out: dict = {"ok": True, "event": event}
    if event in ("staff.arrived", "staff.left"):
        out["result"] = _person(db, delivery_id, event.split(".")[1], data.get("full_name"), data.get("time"), data.get("branch_code"))
    elif event == "visits.hour":
        try:
            d, hour, count = date.fromisoformat(str(data.get("date"))), int(data.get("hour")), int(data.get("count"))
        except (TypeError, ValueError):
            raise BadEvent("visits.hour needs date, hour, count")
        if not (0 <= hour <= 23 and 0 <= count <= 1_000_000):
            raise BadEvent("hour 0..23, count >= 0")
        code = str(data["branch_code"])[:20] if data.get("branch_code") else None
        v = db.scalar(select(CameraVisit).where(CameraVisit.day == d, CameraVisit.hour == hour,
                                                CameraVisit.branch_code.is_(None) if code is None else CameraVisit.branch_code == code))
        if v:
            v.count = count  # the camera sends the hour's total; a re-send replaces it
        else:
            db.add(CameraVisit(day=d, hour=hour, branch_code=code, count=count))
    elif event == "timesheet.day":
        rows = data.get("rows")
        if not isinstance(rows, list) or len(rows) > 5000:
            raise BadEvent("timesheet.day needs rows (max 5000)")
        res, cache = [], {}
        for r in rows:
            if not isinstance(r, dict):
                raise BadEvent("each row must be an object")
            if r.get("first_in"):
                res.append(_person(db, delivery_id, "arrived", r.get("full_name"), r.get("first_in"), r.get("branch_code"), cache))
            if r.get("last_out"):
                res.append(_person(db, delivery_id, "left", r.get("full_name"), r.get("last_out"), r.get("branch_code"), cache))
        out["result"] = dict(Counter(x["match"] for x in res))
    return out


# ---------------- read side (reports, panel) ----------------

def _branch_codes(db: Session, scope: Scope) -> set[str] | None:
    if scope.branch_ids is None:
        return None
    return {b.code for b in db.scalars(select(Branch).where(Branch.id.in_(scope.branch_ids or {-1})))}


def day_summary(db: Session, scope: Scope, d: date) -> dict:
    """Camera facts for a day within the scope. Unmatched names only for whole-network scopes."""
    emps = {e.id: e for e in db.scalars(select(Employee))}
    evs = list(db.scalars(select(CameraEvent).where(CameraEvent.day == d).order_by(CameraEvent.ts)))
    mine = [e for e in evs if e.employee_id and scope.allows_branch(emps[e.employee_id].branch_id)]
    arrived = {}
    for e in mine:
        if e.kind == "arrived" and (e.employee_id not in arrived or e.ts < arrived[e.employee_id]):
            arrived[e.employee_id] = e.ts
    grace = int(cfg("attendance.late_grace_min", 10))
    late = 0
    for emp_id, ts in arrived.items():
        start = sch.planned_start(emps[emp_id], d)
        late += bool(start and ts > start + timedelta(minutes=grace))
    unknown = [e for e in evs if e.match != "matched"]
    codes = _branch_codes(db, scope)
    visits = [v for v in db.scalars(select(CameraVisit).where(CameraVisit.day == d))
              if codes is None or (v.branch_code and v.branch_code in codes)]
    hourly = defaultdict(int)
    for v in visits:
        hourly[v.hour] += v.count
    return {
        "date": d.isoformat(),
        "configured": bool(settings().camera_webhook_secret),
        "arrived": len(arrived), "late": late,
        "unmatched_count": len(unknown) if scope.all_branches else None,
        "unmatched": sorted({f"{e.raw_name} ({e.match})" for e in unknown}) if scope.all_branches else None,
        "hourly_visits": [{"hour": h, "count": hourly[h]} for h in sorted(hourly)],
        "visits_total": sum(hourly.values()),
        "events": [{"id": e.id, "time": e.ts.strftime("%H:%M"), "kind": e.kind, "full_name": emps[e.employee_id].full_name,
                    "branch": emps[e.employee_id].branch.name if emps[e.employee_id].branch else "—",
                    "applied": e.applied, "note": e.note} for e in mine],
    }


def days_overview(db: Session, scope: Scope, days: int = 14, today: date | None = None) -> list[dict]:
    today = today or date.today()
    return [{k: v for k, v in day_summary(db, scope, today - timedelta(days=i)).items() if k not in ("events", "unmatched")}
            for i in range(days)]
