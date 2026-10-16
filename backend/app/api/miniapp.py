"""Telegram Mini App: employee 'Keldim / Ketdim' + team-lead cabinet (rapport, month, entries)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import make_token, miniapp_scope, verify_init_data
from ..config import settings
from ..db import get_db
from ..models import AttendanceEvent, Branch, Employee, LeadReport, PayrollEntry
from ..rbac import Scope, audit, led_branches
from ..services import attendance, payroll, schedules

router = APIRouter(prefix="/api/miniapp")


class AuthIn(BaseModel):
    init_data: str = ""


@router.post("/auth")
def auth(body: AuthIn, db: Session = Depends(get_db)):
    s = settings()
    # the Mini App may be opened from Hamza's bot, Rauf's bot or the hub bot — accept a signature from any of ours
    tokens = [t for t in (s.bot_token("hamza"), s.bot_token("rauf"), s.hub_bot_token) if t]
    if body.init_data and tokens:
        tg = None
        for t in tokens:
            try:
                tg = verify_init_data(body.init_data, t)
                break
            except HTTPException:
                continue
        if tg is None:
            raise HTTPException(401, "Bad Telegram signature")
        tg_id = int(tg["id"])
    elif s.debug and s.dev_telegram_id:
        tg_id = s.dev_telegram_id  # local development in a normal browser
    else:
        raise HTTPException(401, "Open this page from Telegram")
    return {"token": make_token(str(tg_id), "miniapp", 7)}


def _self(scope: Scope, db: Session) -> Employee:
    if not scope.employee_id:
        raise HTTPException(403, "Not linked")
    return db.get(Employee, scope.employee_id)


@router.get("/me")
def me(scope: Scope = Depends(miniapp_scope), db: Session = Depends(get_db)):
    if not scope.employee_id:
        return {"linked": False, "role": scope.role}
    e = _self(scope, db)
    today = date.today()
    data = attendance.AttendanceData(db, [e.id], today.replace(day=1), today)
    res = attendance.compute_day(e, today, data)
    # an overnight shift started yesterday is still open today
    yday = attendance.compute_day(e, today - timedelta(days=1), attendance.AttendanceData(db, [e.id], today - timedelta(days=1), today))
    month = attendance.month_tabel(db, Scope(scope.actor, "owner"), today.strftime("%Y-%m"))
    row = next((r for r in month["rows"] if r["employee_id"] == e.id), None)
    return {"linked": True, "role": scope.role, "full_name": e.full_name, "branch": e.branch.name if e.branch else None,
            "position": e.position.title if e.position else None, "is_lead": bool(led_branches(db, e.id)),
            "today": res.as_dict(), "open_shift_from_yesterday": yday.status == "on_shift",
            "month": {"worked_hours": row["worked_hours"], "worked_days": row["worked_days"], "late_days": row["late_days"]} if row else None}


@router.get("/link/branches")
def link_branches(db: Session = Depends(get_db)):
    return [{"id": b.id, "name": b.name, "city": b.city} for b in db.scalars(select(Branch).order_by(Branch.name))]


@router.get("/link/people")
def link_people(branch_id: int, db: Session = Depends(get_db), scope: Scope = Depends(miniapp_scope)):
    """'pharmacy -> name' search. Only people not yet linked are listed."""
    q = select(Employee).where(Employee.branch_id == branch_id, Employee.status != "fired", Employee.telegram_id.is_(None))
    return [{"id": e.id, "full_name": e.full_name} for e in db.scalars(q.order_by(Employee.full_name))]


class LinkIn(BaseModel):
    employee_id: int
    phone_last4: str = Field(min_length=4, max_length=4)


@router.post("/link")
def link(body: LinkIn, tg_scope: Scope = Depends(miniapp_scope), db: Session = Depends(get_db)):
    tg_id = int(tg_scope.actor.split(":")[1])
    if db.scalar(select(Employee).where(Employee.telegram_id == tg_id)):
        raise HTTPException(409, "This Telegram is already linked")
    e = db.get(Employee, body.employee_id)
    if not e or e.telegram_id:
        raise HTTPException(409, "Already linked — ask HR")
    if not e.phone or not e.phone.replace(" ", "").endswith(body.phone_last4):
        audit(db, tg_scope, "link_failed", f"employee:{e.id}")
        db.commit()
        raise HTTPException(403, "Phone does not match — ask HR")
    e.telegram_id = tg_id
    audit(db, tg_scope, "telegram_linked", f"employee:{e.id}")
    db.commit()
    return {"ok": True}


class CheckIn(BaseModel):
    kind: str  # in | out


@router.post("/check")
def check(body: CheckIn, scope: Scope = Depends(miniapp_scope), db: Session = Depends(get_db)):
    if body.kind not in ("in", "out"):
        raise HTTPException(400, "kind must be in|out")
    e = _self(scope, db)
    last = db.scalar(select(AttendanceEvent).where(AttendanceEvent.employee_id == e.id).order_by(AttendanceEvent.ts.desc()))
    now = datetime.now()
    if last and last.kind == body.kind and (now - last.ts) < timedelta(minutes=2):
        return {"ok": True, "duplicate": True, "ts": last.ts}
    db.add(AttendanceEvent(employee_id=e.id, kind=body.kind, ts=now, source="telegram"))
    payroll.mark_changed(db, now.strftime("%Y-%m"))
    db.commit()
    return {"ok": True, "ts": now}


# ---------------- team-lead cabinet ----------------

def _lead_branches(scope: Scope, db: Session) -> set[int]:
    if scope.at_least("hr_head"):
        return {b.id for b in db.scalars(select(Branch))}
    if not scope.employee_id:
        raise HTTPException(403, "Not a team lead")
    b = led_branches(db, scope.employee_id)
    if not b:
        raise HTTPException(403, "Not a team lead")
    return b


@router.get("/lead/branches")
def lead_branches(scope: Scope = Depends(miniapp_scope), db: Session = Depends(get_db)):
    ids = _lead_branches(scope, db)
    return [{"id": b.id, "name": b.name, "mode": b.mode} for b in db.scalars(select(Branch).where(Branch.id.in_(ids)))]


def _report_window(d: date) -> None:
    today = date.today()
    first = today.replace(day=1)
    if today.day <= 3:
        first = (first - timedelta(days=1)).replace(day=1)
    if d > today or d < first:
        raise HTTPException(400, "Day is outside the reporting window")


@router.get("/lead/report")
def lead_report_get(branch_id: int, day: date | None = None, scope: Scope = Depends(miniapp_scope), db: Session = Depends(get_db)):
    if branch_id not in _lead_branches(scope, db):
        raise HTTPException(403, "Not your branch")
    d = day or date.today()
    s = attendance.day_summary(db, Scope(scope.actor, "owner", {branch_id}), d, branch_id)
    emps = {e.id: e for e in attendance.employees_in_scope(db, Scope(scope.actor, "owner"), branch_id)}
    warns = {}
    for x in db.scalars(select(PayrollEntry).where(PayrollEntry.month == d.strftime("%Y-%m"), PayrollEntry.kind == "warning",
                                                   PayrollEntry.cancelled.is_(False))):
        warns[x.employee_id] = warns.get(x.employee_id, 0) + 1
    for r in s["rows"]:
        e = emps.get(r["employee_id"])
        r["pay_type"] = e.pay_type if e else None
        r["workday"] = schedules.is_workday(e, d) if e else None
        r["warnings_month"] = warns.get(r["employee_id"], 0)
    s["locked"] = payroll.is_locked(db, d.strftime("%Y-%m"))
    return s


class ReportIn(BaseModel):
    employee_id: int
    day: date
    status: str  # came | absent | cancel
    hours: float | None = Field(default=None, ge=0.5, le=24)


@router.post("/lead/report")
def lead_report_set(body: ReportIn, scope: Scope = Depends(miniapp_scope), db: Session = Depends(get_db)):
    e = db.get(Employee, body.employee_id)
    if not e or e.status == "fired" or e.branch_id not in _lead_branches(scope, db):
        audit(db, scope, "access_denied", f"employee:{body.employee_id}")
        db.commit()
        raise HTTPException(403, "This person is not in your branch")
    _report_window(body.day)
    month = body.day.strftime("%Y-%m")
    if payroll.is_locked(db, month):
        raise HTTPException(409, "Month is closed — view only")
    prev = db.scalar(select(LeadReport).where(LeadReport.employee_id == e.id, LeadReport.day == body.day,
                                              LeadReport.cancelled.is_(False)).order_by(LeadReport.id.desc()))
    if prev:
        prev.cancelled = True
    if body.status != "cancel":
        if body.status not in ("came", "absent"):
            raise HTTPException(400, "status must be came|absent|cancel")
        hours = body.hours if body.status == "came" else None
        if body.status == "came" and hours is None:
            hours = schedules.planned_hours(e, body.day) or None
        db.add(LeadReport(employee_id=e.id, day=body.day, status=body.status, hours=hours, author_id=scope.employee_id))
    payroll.mark_changed(db, month)
    audit(db, scope, "lead_report", f"employee:{e.id}", day=str(body.day), status=body.status, hours=body.hours,
          before=prev.status if prev else None)
    db.commit()
    return {"ok": True}


@router.get("/lead/month")
def lead_month(branch_id: int, month: str | None = None, scope: Scope = Depends(miniapp_scope), db: Session = Depends(get_db)):
    if branch_id not in _lead_branches(scope, db):
        raise HTTPException(403, "Not your branch")
    month = month or date.today().strftime("%Y-%m")
    # Team leads see the money of their own team only (set payroll=False here to hide it from heads).
    lead_scope = Scope(scope.actor, "manager", {branch_id}, payroll=True)
    return payroll.payroll_table(db, lead_scope, month, branch_id)


class LeadEntryIn(BaseModel):
    employee_id: int
    kind: str  # advance | penalty | bonus | warning
    amount: int = Field(default=0, ge=0, le=100_000_000)
    reason: str = Field(min_length=3, max_length=300)


@router.post("/lead/entries")
def lead_entry(body: LeadEntryIn, scope: Scope = Depends(miniapp_scope), db: Session = Depends(get_db)):
    e = db.get(Employee, body.employee_id)
    if not e or e.branch_id not in _lead_branches(scope, db):
        raise HTTPException(403, "This person is not in your branch")
    if body.kind not in ("advance", "penalty", "bonus", "warning"):
        raise HTTPException(400, "Bad kind")
    month = date.today().strftime("%Y-%m")
    if payroll.is_locked(db, month) and body.kind != "warning":
        raise HTTPException(409, "Month approved — money entries blocked")
    db.add(PayrollEntry(employee_id=e.id, month=month, kind=body.kind, amount=0 if body.kind == "warning" else body.amount,
                        reason=body.reason, author=scope.actor))
    payroll.mark_changed(db, month)
    audit(db, scope, "lead_entry", f"employee:{e.id}", kind=body.kind, amount=body.amount, reason=body.reason)
    db.commit()
    return {"ok": True}
