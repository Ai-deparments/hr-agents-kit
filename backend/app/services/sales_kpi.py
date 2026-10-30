"""Sales agents ranking for a month (SalesRecord, imported from Smartup): amount, share, rank, Δ vs previous month,
ABC class (thresholds from the KPI analytics settings, default A 80% / B 95%) and the 80/20 fact.
Honest numbers only: no record = unknown (None), never 0; a plan is shown only when config `sales.monthly_plan` sets one."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import cfg
from ..models import AuditLog, Department, Employee, SalesRecord
from ..rbac import Scope
from . import kpi

IMPORT_ACTIONS = ("import_smartup", "sales_import")


def prev_month(month: str) -> str:
    y, m = map(int, month.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def sales_department_id(db: Session) -> int | None:
    d = db.scalar(select(Department).where(Department.name == cfg("imports.smartup.department", "Savdo agentlari")))
    return d.id if d else None


def _amounts(db: Session, scope: Scope, month: str, department_id: int | None, branch_id: int | None) -> dict[int, tuple[Employee, int]]:
    q = select(SalesRecord, Employee).join(Employee, Employee.id == SalesRecord.employee_id).where(SalesRecord.month == month)
    if scope.branch_ids is not None:
        q = q.where(Employee.branch_id.in_(scope.branch_ids or {-1}))
    if department_id:
        q = q.where(Employee.department_id == department_id)
    if branch_id:
        q = q.where(Employee.branch_id == branch_id)
    return {e.id: (e, s.amount) for s, e in db.execute(q)}


def _plan(month: str) -> int | None:
    """`sales.monthly_plan`: a number (every month) or {"YYYY-MM": number}. Absent -> None (no plan is invented)."""
    p = cfg("sales.monthly_plan", None)
    if isinstance(p, dict):
        p = p.get(month)
    try:
        return int(p) if p is not None and float(p) > 0 else None
    except (TypeError, ValueError):
        return None


def ranking(db: Session, scope: Scope, month: str | None = None, branch_id: int | None = None,
            department_id: int | None = None, today: date | None = None) -> dict:
    """department_id None -> the Smartup sales department when it exists, else everyone with sales."""
    today = today or date.today()
    month = month or today.strftime("%Y-%m")
    dept = department_id or sales_department_id(db)
    cur = {k: v for k, v in _amounts(db, scope, month, dept, branch_id).items() if v[1] > 0}
    prev = {k: a for k, (_, a) in _amounts(db, scope, prev_month(month), dept, branch_id).items() if a > 0}
    st = kpi.settings(db)
    items = sorted(cur.items(), key=lambda x: (-x[1][1], x[1][0].full_name))
    total = sum(a for _, (_, a) in items)
    rows, cum = [], 0
    for i, (eid, (e, a)) in enumerate(items, 1):
        before, cum = cum, cum + a
        cls = "A" if before < st["abc_a"] * total / 100 else "B" if before < st["abc_b"] * total / 100 else "C"
        p = prev.get(eid)
        rows.append({"rank": i, "employee_id": eid, "full_name": e.full_name, "branch": e.branch.name if e.branch else None,
                     "status": e.status, "amount": a, "share": round(100 * a / total, 1), "cum_share": round(100 * cum / total, 1),
                     "class": cls, "prev_amount": p, "delta": a - p if p is not None else None,
                     "delta_pct": round(100 * (a - p) / p, 1) if p else None})
    n = len(rows)
    top_n = max(1, round(n * st["pareto_top"] / 100)) if n else 0
    prev_total = sum(prev.values()) if prev else None
    plan = _plan(month) if scope.all_branches and not branch_id and not department_id else None
    return {
        "month": month, "prev_month": prev_month(month), "partial": month == today.strftime("%Y-%m"),
        "n": n, "total": total if n else None, "prev_total": prev_total,
        "delta": total - prev_total if n and prev_total else None,
        "delta_pct": round(100 * (total - prev_total) / prev_total, 1) if n and prev_total else None,
        "counts": {c: sum(1 for r in rows if r["class"] == c) for c in "ABC"},
        "class_share": {c: round(sum(r["amount"] for r in rows if r["class"] == c) * 100 / total, 1) if total else None for c in "ABC"},
        "pareto": {"top_pct": st["pareto_top"], "top_n": top_n,
                   "top_share": round(100 * sum(r["amount"] for r in rows[:top_n]) / total, 1) if total else None},
        "settings": {"abc_a": st["abc_a"], "abc_b": st["abc_b"]},
        "plan": plan, "plan_pct": round(100 * total / plan, 1) if plan and n else None,
        "rows": rows,
    }


def changed_on(db: Session, day: date) -> bool:
    """Did a sales import change any amount on that day (audit trail of the Smartup / CSV importers)?"""
    a = datetime.combine(day, datetime.min.time())
    for r in db.scalars(select(AuditLog).where(AuditLog.action.in_(IMPORT_ACTIONS), AuditLog.ts >= a, AuditLog.ts < a + timedelta(days=1))):
        d = r.details or {}
        if d.get("sales_changed", d.get("rows", 0)):
            return True
    return False
