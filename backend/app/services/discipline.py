"""Discipline rules: N warnings, then a fine. The rule list comes from company.yaml; admins edit the
numbers and texts in the panel (audited with before/after; free texts are logged as lengths only).
Applying a rule is a human action (it creates a payroll 'warning' or 'penalty' entry with a snapshot amount)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import cfg
from ..models import DisciplineCase, DisciplineRule, Employee, PayrollEntry
from ..rbac import Scope, audit
from . import payroll

WINDOWS = ("month", "all_time", "per_case")
EDITABLE = ("title", "text", "window", "warnings_before_fine", "fine_amount", "extra_amount", "note", "starts_on")
TEXT_FIELDS = ("title", "text", "note")
MAX_AMOUNT = 100_000_000


def sync_from_config(db: Session) -> int:
    """Create rules that are in company.yaml but not in the database. Existing rules keep the panel edits."""
    have = {r.code for r in db.scalars(select(DisciplineRule))}
    n = 0
    for r in cfg("discipline.rules", []) or []:
        if r.get("code") and r["code"] not in have:
            db.add(DisciplineRule(code=r["code"], title=r.get("title", r["code"]), text=r.get("text", ""),
                                  window=r.get("window", "month") if r.get("window") in WINDOWS else "month",
                                  warnings_before_fine=int(r.get("warnings_before_fine", 0)),
                                  fine_amount=int(r.get("fine_amount", 0)), extra_amount=int(r.get("extra_amount", 0)),
                                  note=r.get("note", ""), starts_on=date.fromisoformat(str(r["starts_on"])) if r.get("starts_on") else None))
            n += 1
    return n


def rule_dict(r: DisciplineRule) -> dict:
    return {"id": r.id, "code": r.code, "title": r.title, "text": r.text, "window": r.window,
            "warnings_before_fine": r.warnings_before_fine, "fine_amount": r.fine_amount, "extra_amount": r.extra_amount,
            "note": r.note, "starts_on": r.starts_on.isoformat() if r.starts_on else None,
            "updated_at": r.updated_at.isoformat(timespec="minutes") if r.updated_at else None, "updated_by": r.updated_by}


def _for_audit(d: dict) -> dict:
    return {k: ({"len": len(v or "")} if k in TEXT_FIELDS else v) for k, v in d.items()}


def update_rule(db: Session, scope: Scope, rule: DisciplineRule, changes: dict) -> DisciplineRule:
    if "*" not in scope.perms:
        raise PermissionError("Only an administrator edits discipline rules")
    clean = {k: v for k, v in changes.items() if k in EDITABLE}
    if "window" in clean and clean["window"] not in WINDOWS:
        raise ValueError("window must be month, all_time or per_case")
    for k in ("warnings_before_fine",):
        if k in clean and not 0 <= int(clean[k]) <= 20:
            raise ValueError("warnings_before_fine must be 0..20")
    for k in ("fine_amount", "extra_amount"):
        if k in clean and not 0 <= int(clean[k]) <= MAX_AMOUNT:
            raise ValueError(f"{k} out of range")
    if "title" in clean and len((clean["title"] or "").strip()) < 2:
        raise ValueError("Title is required")
    if isinstance(clean.get("starts_on"), str):
        clean["starts_on"] = date.fromisoformat(clean["starts_on"]) if clean["starts_on"] else None
    before = {k: getattr(rule, k) for k in clean}
    for k, v in clean.items():
        setattr(rule, k, v.strip() if isinstance(v, str) else v)
    after = {k: getattr(rule, k) for k in clean}
    changed = [k for k in clean if before[k] != after[k]]
    if changed:
        rule.updated_at, rule.updated_by = datetime.now(), scope.actor
        audit(db, scope, "discipline_rule_update", f"rule:{rule.code}",
              before=_for_audit({k: _plain(before[k]) for k in changed}), after=_for_audit({k: _plain(after[k]) for k in changed}))
    return rule


def _plain(v):
    return v.isoformat() if isinstance(v, date) else v


def prior_count(db: Session, rule: DisciplineRule, employee_id: int, month: str) -> int:
    """Live (not cancelled) earlier cases of this rule for this person inside the rule's window."""
    if rule.window == "per_case":
        return 0
    q = (select(DisciplineCase).join(PayrollEntry, PayrollEntry.id == DisciplineCase.entry_id)
         .where(DisciplineCase.rule_id == rule.id, DisciplineCase.employee_id == employee_id, PayrollEntry.cancelled.is_(False)))
    if rule.window == "month":
        q = q.where(DisciplineCase.month == month)
    elif rule.starts_on:
        q = q.where(DisciplineCase.created_at >= datetime.combine(rule.starts_on, datetime.min.time()))
    return len(list(db.scalars(q)))


def apply_rule(db: Session, scope: Scope, emp: Employee, rule: DisciplineRule, month: str, reason: str,
               today: date | None = None) -> DisciplineCase:
    """Human only. Warning while the person has fewer than N earlier cases in the window, then a fine."""
    if scope.actor.startswith("agent:"):
        raise PermissionError("Only a person applies a discipline rule")
    if not scope.allows_branch(emp.branch_id):
        raise PermissionError("Not your branch")
    if len((reason or "").strip()) < 3:
        raise ValueError("Reason is required")
    today = today or date.today()
    if rule.starts_on and rule.starts_on > today:
        raise ValueError(f"Rule starts on {rule.starts_on.isoformat()}")
    prior = prior_count(db, rule, emp.id, month)
    fine = rule.window == "per_case" or prior >= rule.warnings_before_fine
    if fine and payroll.is_locked(db, month):
        raise ValueError("Month is approved/closed — money entries are blocked")
    amount = (rule.fine_amount + rule.extra_amount) if fine else 0
    entry = PayrollEntry(employee_id=emp.id, month=month, kind="penalty" if fine else "warning", amount=amount,
                         reason=f"[{rule.code}] {rule.title}: {reason.strip()}"[:300], author=scope.actor)
    db.add(entry)
    db.flush()
    case = DisciplineCase(employee_id=emp.id, rule_id=rule.id, month=month, outcome="fine" if fine else "warning",
                          prior_count=prior, fine_amount=rule.fine_amount if fine else 0,
                          extra_amount=rule.extra_amount if fine else 0, entry_id=entry.id, reason=reason.strip()[:300],
                          author=scope.actor)
    db.add(case)
    db.flush()
    payroll.mark_changed(db, month)
    audit(db, scope, "discipline_apply", f"employee:{emp.id}", rule=rule.code, outcome=case.outcome, amount=amount, prior=prior)
    return case


def case_dict(c: DisciplineCase, entry: PayrollEntry | None, show_money: bool) -> dict:
    return {"id": c.id, "employee_id": c.employee_id, "full_name": c.employee.full_name, "rule": c.rule.title,
            "rule_code": c.rule.code, "month": c.month, "outcome": c.outcome, "prior_count": c.prior_count,
            "amount": (c.fine_amount + c.extra_amount) if show_money or c.outcome == "warning" else None,
            "cancelled": bool(entry and entry.cancelled), "reason": c.reason, "author": c.author,
            "created_at": c.created_at.isoformat(timespec="minutes")}


def cases(db: Session, scope: Scope, month: str) -> list[dict]:
    q = select(DisciplineCase).join(Employee).where(DisciplineCase.month == month).order_by(DisciplineCase.id.desc())
    if scope.branch_ids is not None:
        q = q.where(Employee.branch_id.in_(scope.branch_ids or {-1}))
    rows = list(db.scalars(q))
    entries = {e.id: e for e in db.scalars(select(PayrollEntry).where(PayrollEntry.id.in_([c.entry_id for c in rows] or [-1])))}
    return [case_dict(c, entries.get(c.entry_id), scope.payroll) for c in rows]
