"""KPI: metrics with target and weight -> per-employee score; ABC and 80/20 (Pareto) analysis.
score = Σ weight × min(ratio, cap) / Σ weight × 100, ratio = value/target (up) or target/value (down).
Only metrics that have a value count; coverage says how many of the applicable metrics were filled."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import cfg
from ..models import Employee, KpiMetric, KpiValue, SalesRecord, Setting
from ..rbac import Scope

DEFAULT_SETTINGS = {"abc_a": 80, "abc_b": 95, "pareto_top": 20, "min_base": 5}


def settings(db: Session) -> dict:
    s = db.get(Setting, "analytics")
    return {**DEFAULT_SETTINGS, **(s.value if s else {})}


def save_settings(db: Session, data: dict) -> dict:
    a, b, top = int(data.get("abc_a", 80)), int(data.get("abc_b", 95)), int(data.get("pareto_top", 20))
    if not (50 <= a < b <= 99) or not (5 <= top <= 50):
        raise ValueError("Need 50 ≤ A < B ≤ 99 and 5 ≤ top ≤ 50")
    s = db.get(Setting, "analytics") or Setting(key="analytics", value={})
    s.value = {**settings(db), "abc_a": a, "abc_b": b, "pareto_top": top, "min_base": max(1, int(data.get("min_base", 5)))}
    db.merge(s)
    return s.value


def employees(db: Session, scope: Scope, department_id: int | None = None, branch_id: int | None = None) -> list[Employee]:
    q = select(Employee).where(Employee.status != "fired").order_by(Employee.full_name)
    if scope.branch_ids is not None:
        q = q.where(Employee.branch_id.in_(scope.branch_ids or {-1}))
    if department_id:
        q = q.where(Employee.department_id == department_id)
    if branch_id:
        q = q.where(Employee.branch_id == branch_id)
    return list(db.scalars(q))


def applies(m: KpiMetric, e: Employee) -> bool:
    return m.active and (m.position_id is None or m.position_id == e.position_id) and \
        (m.department_id is None or m.department_id == e.department_id)


def ratio(m: KpiMetric, value: float) -> float:
    cap = float(cfg("payroll.kpi_cap", 1.2))
    if m.target <= 0:
        return 0.0
    if m.direction == "down":
        r = cap if value <= 0 else m.target / value
    else:
        r = value / m.target
    return max(0.0, min(r, cap))


def score(metrics: list[KpiMetric], values: dict[int, float]) -> tuple[float | None, int]:
    used = [m for m in metrics if m.id in values]
    w = sum(m.weight for m in used)
    if not used or w == 0:
        return None, 0
    return round(100 * sum(m.weight * ratio(m, values[m.id]) for m in used) / w, 1), len(used)


def grid(db: Session, scope: Scope, month: str, department_id: int | None = None, branch_id: int | None = None) -> dict:
    metrics = list(db.scalars(select(KpiMetric).where(KpiMetric.active.is_(True)).order_by(KpiMetric.id)))
    emps = employees(db, scope, department_id, branch_id)
    vals: dict[int, dict[int, float]] = defaultdict(dict)
    for v in db.scalars(select(KpiValue).where(KpiValue.month == month, KpiValue.employee_id.in_([e.id for e in emps] or [-1]))):
        vals[v.employee_id][v.metric_id] = v.value
    rows = []
    for e in emps:
        mine = [m for m in metrics if applies(m, e)]
        s, used = score(mine, vals[e.id])
        rows.append({"employee_id": e.id, "full_name": e.full_name, "branch": e.branch.name if e.branch else None,
                     "department": e.department.name if e.department else None,
                     "position": e.position.title if e.position else None,
                     "metrics": [m.id for m in mine], "values": {str(k): v for k, v in vals[e.id].items()},
                     "score": s, "filled": used, "applicable": len(mine)})
    scored = [r["score"] for r in rows if r["score"] is not None]
    return {"month": month, "metrics": [metric_row(m) for m in metrics], "rows": rows,
            "avg": round(sum(scored) / len(scored), 1) if scored else None, "scored": len(scored), "total": len(rows)}


def metric_row(m: KpiMetric) -> dict:
    return {"id": m.id, "name": m.name, "unit": m.unit, "direction": m.direction, "target": m.target, "weight": m.weight,
            "position_id": m.position_id, "department_id": m.department_id, "active": m.active}


def abc(db: Session, scope: Scope, month: str, basis: str = "kpi", department_id: int | None = None) -> dict:
    """basis: kpi (score) | sales (personal sales) | metric:<id> (value of one 'up' metric)."""
    st = settings(db)
    emps = employees(db, scope, department_id)
    by_id = {e.id: e for e in emps}
    data: dict[int, float] = {}
    if basis == "kpi":
        for r in grid(db, scope, month, department_id)["rows"]:
            if r["score"] is not None:
                data[r["employee_id"]] = r["score"]
    elif basis == "sales":
        for s in db.scalars(select(SalesRecord).where(SalesRecord.month == month, SalesRecord.employee_id.in_(list(by_id) or [-1]))):
            data[s.employee_id] = float(s.amount)
    elif basis.startswith("metric:"):
        mid = int(basis.split(":")[1])
        m = db.get(KpiMetric, mid)
        if not m or m.direction != "up":
            raise ValueError("ABC works on 'more is better' metrics only")
        for v in db.scalars(select(KpiValue).where(KpiValue.month == month, KpiValue.metric_id == mid,
                                                   KpiValue.employee_id.in_(list(by_id) or [-1]))):
            data[v.employee_id] = v.value
    else:
        raise ValueError("Unknown basis")
    items = sorted(((k, v) for k, v in data.items() if v > 0), key=lambda x: -x[1])
    total = sum(v for _, v in items)
    rows, cum = [], 0.0
    for i, (eid, v) in enumerate(items, 1):
        before = cum
        cum += v
        share = 100 * v / total if total else 0
        cls = "A" if before < st["abc_a"] * total / 100 else "B" if before < st["abc_b"] * total / 100 else "C"
        e = by_id[eid]
        rows.append({"rank": i, "employee_id": eid, "full_name": e.full_name, "branch": e.branch.name if e.branch else None,
                     "department": e.department.name if e.department else None, "value": round(v, 2),
                     "share": round(share, 1), "cum_share": round(100 * cum / total, 1) if total else 0, "class": cls})
    n = len(rows)
    top_n = max(1, round(n * st["pareto_top"] / 100)) if n else 0
    top_share = round(sum(r["value"] for r in rows[:top_n]) / total * 100, 1) if total else None
    counts = {c: sum(1 for r in rows if r["class"] == c) for c in "ABC"}
    return {"month": month, "basis": basis, "settings": st, "rows": rows, "total": round(total, 2), "n": n,
            "too_few": n < st["min_base"], "counts": counts,
            "class_share": {c: round(sum(r["share"] for r in rows if r["class"] == c), 1) for c in "ABC"},
            "pareto": {"top_pct": st["pareto_top"], "top_n": top_n, "top_share": top_share},
            "missing": len(emps) - n}


def trend(db: Session, scope: Scope, months: list[str], department_id: int | None = None) -> list[dict]:
    out = []
    for m in months:
        g = grid(db, scope, m, department_id)
        out.append({"month": m, "avg": g["avg"], "scored": g["scored"], "total": g["total"]})
    return out
