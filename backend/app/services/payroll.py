"""Payroll: attendance -> tabel -> formula -> HUMAN approval. Every number keeps its formula.
accrued = base × (worked + paid absence) / norm ; KPI = base × score/100 (cap 1.2) ;
+ manual bonus + sales % + allowances − penalties − late penalty − advances − other. Tax not computed."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import cfg
from ..models import Employee, PayrollEntry, PeriodStatus, SalesRecord
from ..rbac import Scope
from . import attendance as att
from . import schedules as sch

MONEY_KINDS = {"advance", "bonus", "penalty", "other"}


def period(db: Session, month: str) -> PeriodStatus:
    p = db.get(PeriodStatus, month)
    if not p:
        p = PeriodStatus(month=month)
        db.add(p)
        db.flush()
    return p


def mark_changed(db: Session, month: str) -> None:
    p = period(db, month)
    if p.payroll_status == "calculated":
        p.changed_after_calc = True


def is_locked(db: Session, month: str) -> bool:
    p = db.get(PeriodStatus, month)
    return bool(p and (p.tabel_closed or p.payroll_status in ("approved", "paid", "closed")))


def _entries(db: Session, emp_ids: list[int], month: str) -> dict[int, list[PayrollEntry]]:
    out = defaultdict(list)
    for e in db.scalars(select(PayrollEntry).where(PayrollEntry.employee_id.in_(emp_ids or [-1]),
                                                   PayrollEntry.month == month, PayrollEntry.cancelled.is_(False))):
        out[e.employee_id].append(e)
    return out


def calc_employee(emp: Employee, month: str, trow: dict, entries: list[PayrollEntry], sales: int | None,
                  paid_absence_hours: float) -> dict:
    base = emp.base_salary
    norm = trow["norm_hours"]
    worked = trow["worked_hours"]
    lines: list[str] = []
    sums = defaultdict(int)
    for e in entries:
        if e.kind in MONEY_KINDS:
            sums[e.kind] += e.amount
    warnings = sum(1 for e in entries if e.kind == "warning")
    kpi_scores = [e.amount for e in entries if e.kind == "kpi"]

    if base is None:
        return {"employee_id": emp.id, "full_name": emp.full_name, "known": False, "base": None, "norm_hours": norm,
                "worked_hours": worked, "accrued": None, "kpi": None, "bonus": sums["bonus"], "sales_bonus": None,
                "allowances": None, "penalty": sums["penalty"], "late_penalty": 0, "advance": sums["advance"],
                "other": sums["other"], "total": None, "warnings": warnings,
                "explain": ["Salary unknown — not included in totals"]}

    if emp.pay_type == "hourly":
        accrued = round(base * (worked + paid_absence_hours))
        lines.append(f"accrued = {base} × ({worked} + {paid_absence_hours}) h = {accrued}")
    elif emp.pay_type == "daily":
        accrued = round(base * trow["worked_days"])
        lines.append(f"accrued = {base} × {trow['worked_days']} days = {accrued}")
    else:
        accrued = round(base * (worked + paid_absence_hours) / norm) if norm else 0
        lines.append(f"accrued = {base} × ({worked} + {paid_absence_hours}) / {norm} = {accrued}")

    kpi = 0
    if kpi_scores:
        cap = float(cfg("payroll.kpi_cap", 1.2))
        kpi = round(base * min(kpi_scores[-1] / 100, cap))
        lines.append(f"KPI = {base} × min({kpi_scores[-1]}/100, {cap}) = {kpi}")

    sales_bonus = 0
    if cfg("payroll.sales_percent.enabled", False) and sales:
        rate = float(cfg("payroll.sales_percent.default_rate", 0))
        sales_bonus = round(sales * rate)
        lines.append(f"sales bonus = {sales} × {rate} = {sales_bonus}")

    allowances = sum(int(v) for v in (emp.allowances or {}).values())
    if allowances:
        lines.append(f"allowances = {allowances}")

    late_penalty = 0
    lp = cfg("payroll.late_penalty", {}) or {}
    if lp.get("enabled") and norm:
        hourly = base / norm
        grace = lp.get("grace_min", 15)
        blocks = sum(max(c.get("l", 0) - grace, 0) // 30 for c in trow["cells"])
        late_penalty = min(round(blocks * hourly * lp.get("per_30_min_share_of_hour", 0.5)),
                           round(base * lp.get("max_share_of_salary", 0.1)))
        if late_penalty:
            lines.append(f"late penalty = {late_penalty}")

    total = accrued + kpi + sums["bonus"] + sales_bonus + allowances - sums["penalty"] - late_penalty - sums["advance"] - sums["other"]
    lines.append(f"to pay = {total}")
    return {"employee_id": emp.id, "full_name": emp.full_name, "known": True, "base": base, "norm_hours": norm,
            "worked_hours": worked, "accrued": accrued, "kpi": kpi, "bonus": sums["bonus"], "sales_bonus": sales_bonus,
            "allowances": allowances, "penalty": sums["penalty"], "late_penalty": late_penalty,
            "advance": sums["advance"], "other": sums["other"], "total": total, "warnings": warnings, "explain": lines}


def payroll_table(db: Session, scope: Scope, month: str, branch_id: int | None = None, now: datetime | None = None) -> dict:
    tabel = att.month_tabel(db, scope, month, branch_id, now)
    ids = [r["employee_id"] for r in tabel["rows"]]
    emps = {e.id: e for e in db.scalars(select(Employee).where(Employee.id.in_(ids or [-1])))}
    entries = _entries(db, ids, month)
    sales = {s.employee_id: s.amount for s in db.scalars(select(SalesRecord).where(SalesRecord.month == month))}
    rows = []
    for tr in tabel["rows"]:
        emp = emps[tr["employee_id"]]
        paid_abs = sum(sch.planned_hours(emp, sch.month_days(month)[c["d"] - 1]) for c in tr["cells"] if c["s"] == "leave")
        row = calc_employee(emp, month, tr, entries.get(emp.id, []), sales.get(emp.id), paid_abs)
        row["branch"] = tr["branch"]
        row["position"] = tr["position"]
        if not scope.payroll:  # amounts never leave the server without payroll permission
            row = {k: (None if k in {"base", "accrued", "kpi", "bonus", "sales_bonus", "allowances", "penalty",
                                     "late_penalty", "advance", "other", "total"} else v) for k, v in row.items()}
            row["explain"] = []
        rows.append(row)
    p = db.get(PeriodStatus, month)
    known = [r for r in rows if r.get("total") is not None]
    return {"month": month, "status": p.payroll_status if p else "draft", "tabel_closed": bool(p and p.tabel_closed),
            "changed_after_calc": bool(p and p.changed_after_calc), "amounts_visible": scope.payroll,
            "fund": sum(r["total"] for r in known) if scope.payroll else None,
            "unknown_salary": sum(1 for r in rows if not r["known"]), "rows": rows}


def precheck(db: Session, scope: Scope, month: str, now: datetime | None = None) -> dict:
    """What could be paid wrong. Never fixes anything itself."""
    tabel = att.month_tabel(db, scope, month, None, now)
    ids = [r["employee_id"] for r in tabel["rows"]]
    emps = {e.id: e for e in db.scalars(select(Employee).where(Employee.id.in_(ids or [-1])))}
    entries = _entries(db, ids, month)
    issues = []
    default_limit = float(cfg("attendance.overtime_limit_hours", 40))
    by_sched = cfg("attendance.overtime_limit_by_schedule", {}) or {}
    for tr in tabel["rows"]:
        emp = emps[tr["employee_id"]]
        hourly = (emp.base_salary / tr["norm_hours"]) if emp.base_salary and tr["norm_hours"] else None

        def add(kind, detail, risk=None):
            issues.append({"type": kind, "employee_id": emp.id, "full_name": emp.full_name, "branch": tr["branch"],
                           "detail": detail, "amount_at_risk": round(risk) if (risk and scope.payroll) else None})

        if emp.base_salary is None:
            add("no_contract_salary", "Salary unknown — excluded from calculation")
        if tr["worked_hours"] == 0 and not any(c["s"] == "leave" for c in tr["cells"]):
            add("no_hours", "No worked hours in the month")
        if tr["review_days"]:
            add("needs_review_days", f"{tr['review_days']} day(s) need review (missing check-out or conflict)",
                hourly * 8 * tr["review_days"] if hourly else None)
        if tr["unknown_days"]:
            add("unmarked_shifts", f"{tr['unknown_days']} scheduled shift(s) without any mark",
                hourly * 8 * tr["unknown_days"] if hourly else None)
        limit = float(by_sched.get(emp.schedule_code, default_limit))
        if tr["overtime_hours"] > limit:
            add("overtime_over_limit", f"Overtime {tr['overtime_hours']}h > limit {limit}h",
                hourly * (tr["overtime_hours"] - limit) if hourly else None)
        streak = best = 0
        for c in tr["cells"]:
            streak = streak + 1 if c["s"] in ("absent",) else 0
            best = max(best, streak)
        if best >= 3:
            add("absent_3_in_row", f"{best} absences in a row — lead must confirm reason")
        for e in entries.get(emp.id, []):
            if e.kind == "bonus" and emp.base_salary and e.amount > 0.3 * emp.base_salary:
                add("large_bonus", f"Bonus {e.amount} > 30% of salary — confirm basis: '{e.reason}'", e.amount)
    p = db.get(PeriodStatus, month)
    if p and p.changed_after_calc:
        issues.append({"type": "changed_after_calc", "employee_id": None, "full_name": "—", "branch": "—",
                       "detail": "Data changed after calculation — recalculate before approval", "amount_at_risk": None})
    risk = sum(i["amount_at_risk"] or 0 for i in issues)
    return {"month": month, "issues": issues, "count": len(issues),
            "amount_at_risk": risk if scope.payroll else None,
            "base": f"{len(tabel['rows'])} employees, month {month}"}
