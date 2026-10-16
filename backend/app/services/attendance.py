"""Day calculation. Priority: HR edit > HR leave/sick > team-lead report > self check-in.
Rules: 'unmarked' never means 'absent'; missing check-out -> needs_review (8h never assumed);
no source -> unknown, not 0."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..config import cfg
from ..models import Absence, AttendanceEvent, Employee, HrOverride, LeadReport
from ..rbac import Scope
from . import schedules as sch

PRESENT = {"present", "late", "on_shift"}


@dataclass
class DayResult:
    employee_id: int
    day: str
    status: str            # present | late | on_shift | absent | leave | unmarked | off | needs_review | conflict | not_employed
    source: str | None     # hr | leave | lead | telegram | turnstile
    check_in: str | None = None
    check_out: str | None = None
    worked_hours: float | None = None
    planned_hours: float = 0.0
    late_min: int = 0
    overtime_hours: float = 0.0
    leave_kind: str | None = None
    note: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


class AttendanceData:
    """Prefetches everything for a set of employees and a date range (no N+1 queries)."""

    def __init__(self, db: Session, emp_ids: list[int], start: date, end: date):
        self.events: dict[int, list[AttendanceEvent]] = defaultdict(list)
        self.overrides: dict[tuple[int, date], HrOverride] = {}
        self.reports: dict[tuple[int, date], LeadReport] = {}
        self.absences: dict[int, list[Absence]] = defaultdict(list)
        if not emp_ids:
            return
        t0 = datetime.combine(start, datetime.min.time())
        t1 = sch.window_end(end)
        for e in db.scalars(select(AttendanceEvent).where(AttendanceEvent.employee_id.in_(emp_ids),
                                                          AttendanceEvent.ts >= t0, AttendanceEvent.ts <= t1)
                            .order_by(AttendanceEvent.ts)):
            self.events[e.employee_id].append(e)
        for o in db.scalars(select(HrOverride).where(HrOverride.employee_id.in_(emp_ids), HrOverride.day.between(start, end))
                            .order_by(HrOverride.id)):
            self.overrides[(o.employee_id, o.day)] = o
        for r in db.scalars(select(LeadReport).where(LeadReport.employee_id.in_(emp_ids), LeadReport.day.between(start, end),
                                                     LeadReport.cancelled.is_(False)).order_by(LeadReport.id)):
            self.reports[(r.employee_id, r.day)] = r
        for a in db.scalars(select(Absence).where(Absence.employee_id.in_(emp_ids),
                                                  and_(Absence.date_from <= end, Absence.date_to >= start))):
            self.absences[a.employee_id].append(a)


def _fmt(ts: datetime | None) -> str | None:
    return ts.strftime("%Y-%m-%d %H:%M") if ts else None


def _worked(emp: Employee, t_in: datetime, t_out: datetime) -> float:
    hours = (t_out - t_in).total_seconds() / 3600
    if hours > 5:
        hours -= sch.lunch_hours(emp)
    return round(max(hours, 0), 2)


def compute_day(emp: Employee, d: date, data: AttendanceData, now: datetime | None = None) -> DayResult:
    now = now or datetime.now()
    planned = sch.planned_hours(emp, d)
    r = DayResult(emp.id, d.isoformat(), "unmarked", None, planned_hours=planned)
    if not sch.employed_on(emp, d):
        r.status, r.planned_hours = "not_employed", 0
        return r
    grace = int(cfg("attendance.late_grace_min", 10))
    start = sch.planned_start(emp, d)

    def finish(t_in, t_out, src):
        r.source, r.check_in, r.check_out = src, _fmt(t_in), _fmt(t_out)
        if t_in and start and t_in > start + timedelta(minutes=grace):
            r.late_min = int((t_in - start).total_seconds() // 60)
        if t_in and t_out:
            r.worked_hours = _worked(emp, t_in, t_out)
            r.overtime_hours = round(max(r.worked_hours - planned, 0), 2) if planned else r.worked_hours
            r.status = "late" if r.late_min else "present"
        return r

    # 1. HR manual edit
    o = data.overrides.get((emp.id, d))
    if o:
        r.note = f"HR: {o.reason}"
        finish(o.check_in, o.check_out, "hr")
        if not o.check_out:
            r.status = "needs_review"
        return r

    # 2. Leave / sick from HR
    for a in data.absences.get(emp.id, []):
        if a.date_from <= d <= a.date_to:
            r.status, r.source, r.leave_kind = "leave", "leave", a.kind
            return r

    # self check-in (used by 3 and 4)
    ins = [e for e in data.events.get(emp.id, []) if e.kind == "in" and e.ts.date() == d]
    t_in = ins[0].ts if ins else None
    t_out = None
    src_events = ins[0].source if ins else None
    if t_in:
        # the shift ends at the last check-out before the next shift's check-in (or the 30h window)
        nxt = [e.ts for e in data.events.get(emp.id, []) if e.kind == "in" and e.ts.date() > d]
        limit = min([t_in + sch.SHIFT_WINDOW] + nxt)
        outs = [e.ts for e in data.events.get(emp.id, []) if e.kind == "out" and t_in < e.ts <= limit]
        t_out = outs[-1] if outs else None

    # 3. Team-lead report
    rep = data.reports.get((emp.id, d))
    if rep:
        if rep.status == "absent":
            if t_in:
                r.status, r.source, r.check_in = "conflict", "lead", _fmt(t_in)
                r.note = "Lead said absent, but check-in exists — HR must review"
                return r
            r.status, r.source = "absent", "lead"
            return r
        r.source = "lead"
        r.worked_hours = float(rep.hours) if rep.hours is not None else planned or None
        r.overtime_hours = round(max((r.worked_hours or 0) - planned, 0), 2) if planned else (r.worked_hours or 0)
        r.check_in = _fmt(t_in)
        if t_in and start and t_in > start + timedelta(minutes=grace):
            r.late_min = int((t_in - start).total_seconds() // 60)
        r.status = "late" if r.late_min else "present"
        return r

    # 4. Self check-in (Telegram Mini App) / turnstile
    if t_in:
        finish(t_in, t_out, src_events)
        if not t_out:
            if now <= t_in + sch.SHIFT_WINDOW:
                r.status = "on_shift"
            else:
                r.status, r.note = "needs_review", "No check-out — not assuming 8h"
        return r

    if not sch.is_workday(emp, d):
        r.status = "off"
    return r


def employees_in_scope(db: Session, scope: Scope, branch_id: int | None = None, active_on: date | None = None) -> list[Employee]:
    q = select(Employee).order_by(Employee.full_name)
    if scope.branch_ids is not None:
        q = q.where(Employee.branch_id.in_(scope.branch_ids or {-1}))
    if branch_id:
        if not scope.allows_branch(branch_id):
            return []
        q = q.where(Employee.branch_id == branch_id)
    emps = list(db.scalars(q))
    if active_on:
        emps = [e for e in emps if sch.employed_on(e, active_on) and (e.status != "fired" or (e.fire_date and e.fire_date >= active_on))]
    return emps


def day_summary(db: Session, scope: Scope, d: date, branch_id: int | None = None, now: datetime | None = None) -> dict:
    emps = employees_in_scope(db, scope, branch_id, active_on=d)
    data = AttendanceData(db, [e.id for e in emps], d, d)
    rows, by_branch = [], defaultdict(lambda: defaultdict(int))
    for e in emps:
        res = compute_day(e, d, data, now)
        rows.append({**res.as_dict(), "full_name": e.full_name, "branch": e.branch.name if e.branch else "—",
                     "branch_id": e.branch_id, "position": e.position.title if e.position else "—"})
        b = by_branch[e.branch.name if e.branch else "—"]
        b["total"] += 1
        b[res.status] += 1
        if res.status in PRESENT:
            b["came"] += 1
    totals = defaultdict(int)
    for r in rows:
        totals[r["status"]] += 1
    scheduled = sum(1 for r in rows if r["status"] != "off")
    came = sum(totals[s] for s in PRESENT)
    return {
        "date": d.isoformat(),
        "total": len(rows),
        "scheduled": scheduled,
        "came": came,
        "late": totals["late"],
        "unmarked": totals["unmarked"],
        "absent": totals["absent"],
        "leave": totals["leave"],
        "off": totals["off"],
        "needs_review": totals["needs_review"],
        "conflict": totals["conflict"],
        "on_shift": totals["on_shift"],
        "by_branch": {k: dict(v) for k, v in sorted(by_branch.items())},
        "rows": rows,
        "note": "unmarked does not mean absent",
    }


CODES = {"present": "+", "late": "L", "on_shift": "~", "absent": "A", "leave": "V", "unmarked": "?",
         "off": "·", "needs_review": "R", "conflict": "!", "not_employed": " "}


def month_tabel(db: Session, scope: Scope, month: str, branch_id: int | None = None, now: datetime | None = None) -> dict:
    days = sch.month_days(month)
    emps = [e for e in employees_in_scope(db, scope, branch_id) if any(sch.employed_on(e, d) for d in days)]
    data = AttendanceData(db, [e.id for e in emps], days[0], days[-1])
    out = []
    for e in emps:
        cells, worked, late_days, unknown, review, worked_days, overtime = [], 0.0, 0, 0, 0, 0, 0.0
        for d in days:
            if d > (now or datetime.now()).date():
                cells.append({"d": d.day, "s": "future", "c": "", "h": None, "src": None, "l": 0})
                continue
            res = compute_day(e, d, data, now)
            cells.append({"d": d.day, "s": res.status, "c": CODES[res.status], "h": res.worked_hours, "src": res.source, "l": res.late_min})
            if res.worked_hours:
                worked += res.worked_hours
                worked_days += 1
                overtime += res.overtime_hours
            late_days += res.status == "late"
            unknown += res.status == "unmarked" and sch.is_workday(e, d) and d <= (now or datetime.now()).date()
            review += res.status in ("needs_review", "conflict")
        out.append({"employee_id": e.id, "full_name": e.full_name, "branch": e.branch.name if e.branch else "—",
                    "position": e.position.title if e.position else "—", "cells": cells,
                    "worked_hours": round(worked, 2), "worked_days": worked_days, "late_days": late_days,
                    "unknown_days": unknown, "review_days": review, "overtime_hours": round(overtime, 2),
                    "norm_hours": sch.norm_hours(e, month)})
    return {"month": month, "days": [d.day for d in days], "rows": out}


def attendance_rate(db: Session, scope: Scope, days: int, branch_id: int | None = None, today: date | None = None) -> dict:
    today = today or date.today()
    start = today - timedelta(days=days - 1)
    emps = employees_in_scope(db, scope, branch_id)
    data = AttendanceData(db, [e.id for e in emps], start, today)
    scheduled = came = 0
    per = []
    for e in emps:
        miss = late = 0
        d = start
        while d <= today:
            if sch.employed_on(e, d) and sch.is_workday(e, d):
                res = compute_day(e, d, data)
                scheduled += 1
                came += res.status in PRESENT
                miss += res.status in ("absent", "unmarked")
                late += res.status == "late"
            d += timedelta(days=1)
        per.append({"full_name": e.full_name, "branch": e.branch.name if e.branch else "—", "missed": miss, "late": late})
    per.sort(key=lambda x: (-x["missed"], -x["late"]))
    return {"period_days": days, "from": start.isoformat(), "to": today.isoformat(), "scheduled_shifts": scheduled,
            "came": came, "rate_pct": round(100 * came / scheduled, 1) if scheduled else None,
            "base": f"{len(emps)} people, {scheduled} scheduled shifts", "top": per[:10]}
