"""HR analytics: always with base and period; small groups -> counts, not %."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import cfg
from ..models import Candidate, Employee, LeaveRequest, Vacancy
from ..rbac import Scope


def pct(part: int, base: int) -> str:
    """'<10 people -> number, not percent' rule from the analytics persona."""
    if base == 0:
        return "no data"
    if base < 10:
        return f"{part} of {base}" + (" (% unreliable)" if base <= 3 else "")
    return f"{round(100 * part / base, 1)}% ({part} of {base})"


def _emps(db: Session, scope: Scope) -> list[Employee]:
    q = select(Employee)
    if scope.branch_ids is not None:
        q = q.where(Employee.branch_id.in_(scope.branch_ids or {-1}))
    return list(db.scalars(q))


def _key(e: Employee, by: str) -> str:
    if by == "region":
        return e.branch.region.name if e.branch and e.branch.region else "—"
    if by == "position":
        return e.position.title if e.position else "—"
    if by == "status":
        return e.status
    return e.branch.name if e.branch else "—"


def headcount(db: Session, scope: Scope, by: str = "branch") -> dict:
    active = [e for e in _emps(db, scope) if e.status != "fired"]
    c = Counter(_key(e, by) for e in active)
    return {"by": by, "total": len(active), "probation": sum(e.status == "probation" for e in active),
            "groups": dict(sorted(c.items()))}


def turnover(db: Session, scope: Scope, months: int = 3, by: str = "branch", today: date | None = None) -> dict:
    today = today or date.today()
    start = today - timedelta(days=30 * months)
    emps = _emps(db, scope)
    left = [e for e in emps if e.fire_date and start <= e.fire_date <= today]
    avg_base = [e for e in emps if (not e.hire_date or e.hire_date <= today) and (not e.fire_date or e.fire_date >= start)]
    groups = defaultdict(lambda: {"left": 0, "base": 0})
    for e in avg_base:
        groups[_key(e, by)]["base"] += 1
    for e in left:
        groups[_key(e, by)]["left"] += 1
    early = [e for e in left if e.hire_date and (e.fire_date - e.hire_date).days <= 30]
    return {"period": f"{start.isoformat()}..{today.isoformat()}", "months": months, "left": len(left),
            "base": len(avg_base), "rate": pct(len(left), len(avg_base)),
            "left_first_30_days": len(early),
            "groups": {k: {**v, "rate": pct(v["left"], v["base"])} for k, v in sorted(groups.items())}}


def vacancies_sla(db: Session, scope: Scope, today: date | None = None) -> list[dict]:
    today = today or date.today()
    q = select(Vacancy).where(Vacancy.status == "open")
    if scope.branch_ids is not None:
        q = q.where(Vacancy.branch_id.in_(scope.branch_ids or {-1}))
    out = []
    for v in db.scalars(q):
        days_open = (today - v.opened_at).days if v.opened_at else 0
        ratio = days_open / v.sla_days if v.sla_days else 0
        light = "red" if ratio > 1 else "yellow" if ratio >= 0.7 else "green"
        n = len(list(db.scalars(select(Candidate.id).where(Candidate.vacancy_id == v.id))))
        out.append({"id": v.id, "title": v.title, "branch": v.branch.name if v.branch else None, "days_open": days_open,
                    "sla_days": v.sla_days, "light": light, "candidates": n})
    return sorted(out, key=lambda x: -x["days_open"])


def overview(db: Session, scope: Scope, today: date | None = None) -> dict:
    from . import attendance as att
    today = today or date.today()
    emps = _emps(db, scope)
    active = [e for e in emps if e.status != "fired"]
    day = att.day_summary(db, scope, today)
    q = select(LeaveRequest).join(Employee).where(LeaveRequest.status == "pending")
    if scope.branch_ids is not None:
        q = q.where(Employee.branch_id.in_(scope.branch_ids or {-1}))
    pending = len(list(db.scalars(q)))
    cq = select(Candidate).where(Candidate.status == "new")
    new_cands = len(list(db.scalars(cq)))
    fund = sum(e.base_salary or 0 for e in active) if scope.payroll else None
    by_branch = defaultdict(lambda: {"people": 0, "fund": 0})
    for e in active:
        b = by_branch[e.branch.name if e.branch else "—"]
        b["people"] += 1
        b["fund"] += e.base_salary or 0
    rows = [{"branch": k, "people": v["people"], "fund": v["fund"] if scope.payroll else None,
             "avg_salary": round(v["fund"] / v["people"]) if scope.payroll and v["people"] else None}
            for k, v in sorted(by_branch.items())]
    return {"date": today.isoformat(), "active": len(active), "fund": fund,
            "on_shift_today": day["came"], "scheduled_today": day["scheduled"], "late_today": day["late"],
            "unmarked_today": day["unmarked"], "pending_requests": pending, "new_candidates": new_cands,
            "attendance_source": cfg("attendance.source", "telegram"), "branches": rows}
