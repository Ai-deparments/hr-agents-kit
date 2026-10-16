"""SOP read-receipts, anonymous eNPS / exit pulse, and turnover-risk signals (HR-only, never a decision)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import cfg
from ..models import Employee, LeaveRequest, PayrollEntry, PulseResponse, PulseSent, Sop, SopAck
from ..rbac import Scope, audit
from . import attendance as att

MIN_GROUP = 5  # anonymity: no aggregate is shown for fewer answers than this
EXIT_REASONS = ["pay", "schedule", "manager", "workload", "growth", "personal", "other"]


# ---------------- SOP acknowledgement ----------------

def sop_version(s: Sop) -> str:
    return (s.updated_at or datetime(2000, 1, 1)).strftime("%Y%m%d%H%M%S")


def sops_for(db: Session, emp: Employee) -> list[Sop]:
    code = emp.position.code if emp.position else None
    return list(db.scalars(select(Sop).where(or_(Sop.position_code == code, Sop.position_code.is_(None)))))


def my_unread(db: Session, emp: Employee) -> list[dict]:
    acked = {(a.sop_id, a.version) for a in db.scalars(select(SopAck).where(SopAck.employee_id == emp.id))}
    return [{"id": s.id, "title": s.title, "excerpt": s.body[:400]}
            for s in sops_for(db, emp) if (s.id, sop_version(s)) not in acked]


def acknowledge(db: Session, scope: Scope, emp: Employee, sop_id: int) -> dict:
    s = db.get(Sop, sop_id)
    if not s or s not in sops_for(db, emp):
        raise ValueError("This rule is not assigned to your position")
    v = sop_version(s)
    if not db.scalar(select(SopAck).where(SopAck.sop_id == s.id, SopAck.employee_id == emp.id, SopAck.version == v)):
        db.add(SopAck(sop_id=s.id, employee_id=emp.id, version=v))
        audit(db, scope, "sop_ack", f"sop:{s.id}", version=v)
    return {"sop_id": s.id, "title": s.title, "acknowledged": True}


def sop_coverage(db: Session, scope: Scope) -> list[dict]:
    """Per SOP: how many of the people it applies to have read the CURRENT version."""
    emps = [e for e in att.employees_in_scope(db, scope) if e.status != "fired"]
    acks = {(a.sop_id, a.employee_id, a.version) for a in db.scalars(select(SopAck))}
    out = []
    for s in db.scalars(select(Sop).order_by(Sop.title)):
        target = [e for e in emps if s.position_code is None or (e.position and e.position.code == s.position_code)]
        done = sum((s.id, e.id, sop_version(s)) in acks for e in target)
        out.append({"id": s.id, "title": s.title, "position": s.position_code or "all", "target": len(target),
                    "read": done, "pct": round(100 * done / len(target)) if target else None})
    return out


# ---------------- anonymous pulse (eNPS) and exit survey ----------------

def record_pulse(db: Session, emp: Employee, kind: str, score: int, reason: str | None = None, comment: str | None = None) -> bool:
    month = date.today().strftime("%Y-%m")
    if not 0 <= score <= 10:
        raise ValueError("score 0..10")
    sent = db.scalar(select(PulseSent).where(PulseSent.employee_id == emp.id, PulseSent.kind == kind, PulseSent.month == month))
    if sent and sent.answered:
        return False  # one vote per person per month
    if not sent:
        sent = PulseSent(employee_id=emp.id, kind=kind, month=month)
        db.add(sent)
    sent.answered = True
    db.add(PulseResponse(kind=kind, month=month, branch_id=emp.branch_id, score=score,
                         reason=reason if reason in EXIT_REASONS else None, comment=(comment or "")[:500] or None))
    return True


def enps(scores: list[int]) -> int | None:
    if len(scores) < MIN_GROUP:
        return None
    prom = sum(s >= 9 for s in scores)
    det = sum(s <= 6 for s in scores)
    return round(100 * (prom - det) / len(scores))


def pulse_summary(db: Session, scope: Scope, months: int = 3) -> dict:
    since = (date.today().replace(day=1) - timedelta(days=31 * (months - 1))).strftime("%Y-%m")
    rows = [r for r in db.scalars(select(PulseResponse).where(PulseResponse.month >= since))
            if scope.branch_ids is None or r.branch_id in scope.branch_ids]
    by_month, by_branch = defaultdict(list), defaultdict(list)
    for r in rows:
        if r.kind == "enps":
            by_month[r.month].append(r.score)
            by_branch[r.branch_id].append(r.score)
    exits = [r for r in rows if r.kind == "exit"]
    reasons = defaultdict(int)
    for r in exits:
        reasons[r.reason or "other"] += 1
    return {
        "min_group": MIN_GROUP,
        "enps_by_month": {m: {"answers": len(v), "enps": enps(v)} for m, v in sorted(by_month.items())},
        "enps_by_branch": {str(b): {"answers": len(v), "enps": enps(v)} for b, v in by_branch.items()},
        "exit_answers": len(exits),
        "exit_reasons": dict(reasons) if len(exits) >= MIN_GROUP else None,
        "comments": [r.comment for r in rows if r.comment][:50] if len(rows) >= MIN_GROUP else [],
    }


# ---------------- turnover-risk signals (rules, explainable, HR-only) ----------------

def risk_signals(db: Session, scope: Scope, today: date | None = None) -> list[dict]:
    """Simple explainable rules. A signal is a reason to talk, never a decision about a person."""
    today = today or date.today()
    emps = [e for e in att.employees_in_scope(db, scope) if e.status != "fired"]
    d0 = today - timedelta(days=30)
    data = att.AttendanceData(db, [e.id for e in emps], d0 - timedelta(days=30), today)
    warns = defaultdict(int)
    for w in db.scalars(select(PayrollEntry).where(PayrollEntry.kind == "warning", PayrollEntry.cancelled.is_(False),
                                                   PayrollEntry.created_at >= datetime.combine(d0, datetime.min.time()))):
        warns[w.employee_id] += 1
    swaps = defaultdict(int)
    for r in db.scalars(select(LeaveRequest).where(LeaveRequest.kind.in_(["shift_swap", "sick_leave"]),
                                                   LeaveRequest.created_at >= datetime.combine(d0, datetime.min.time()))):
        swaps[r.employee_id] += 1
    out = []
    for e in emps:
        reasons = []

        def period(a: date, b: date):
            late = miss = 0
            d = a
            while d <= b:
                r = att.compute_day(e, d, data)
                late += r.status == "late"
                miss += r.status == "absent"
                d += timedelta(days=1)
            return late, miss
        late_now, miss_now = period(d0, today)
        late_before, miss_before = period(d0 - timedelta(days=30), d0 - timedelta(days=1))
        if late_now >= 3 and late_now > late_before:
            reasons.append(f"late {late_now}× in 30 days (was {late_before})")
        if miss_now >= 2 and miss_now > miss_before:
            reasons.append(f"absent {miss_now}× in 30 days (was {miss_before})")
        if e.hire_date and (today - e.hire_date).days <= 90:
            reasons.append("first 90 days (highest-risk period)")
        if warns[e.id]:
            reasons.append(f"{warns[e.id]} warning(s) this month")
        if swaps[e.id] >= 2:
            reasons.append(f"{swaps[e.id]} shift-swap / sick requests in 30 days")
        if len(reasons) >= 2:
            out.append({"employee_id": e.id, "full_name": e.full_name, "branch": e.branch.name if e.branch else "—",
                        "signals": reasons, "level": "high" if len(reasons) >= 3 else "medium"})
    return sorted(out, key=lambda x: -len(x["signals"]))
