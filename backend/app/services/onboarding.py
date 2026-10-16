"""30/60/90 onboarding with checklist templates per position + mentor + test scores.
Facts only: probation decision is always the manager's."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import cfg
from ..models import Employee, OnboardingItem, OnboardingPlan
from ..rbac import Scope, audit


class NotAllowed(Exception):
    pass


def stage_for_day(day: int) -> int:
    return 30 if day <= 30 else 60 if day <= 60 else 90


def score_label(score: int) -> str:
    if score >= int(cfg("onboarding.test_good", 80)):
        return "good"
    if score >= int(cfg("onboarding.test_ok", 60)):
        return "satisfactory"
    return "low — notify manager"


def light(progress: float) -> str:
    if progress < cfg("onboarding.light_red_below", 60):
        return "red"
    if progress < cfg("onboarding.light_yellow_below", 85):
        return "yellow"
    return "green"


def create_plan(db: Session, scope: Scope, emp: Employee, mentor: str | None = None, start: date | None = None) -> OnboardingPlan:
    if not scope.at_least("hr_head") and scope.role not in ("admin", "hr_manager"):
        raise NotAllowed("Only HR can add a new hire to onboarding")
    existing = db.scalar(select(OnboardingPlan).where(OnboardingPlan.employee_id == emp.id))
    if existing:
        return existing
    templates = cfg("onboarding.templates", {}) or {}
    code = emp.position.code if emp.position else "default"
    tpl = templates.get(code) or templates.get("default") or {}
    plan = OnboardingPlan(employee_id=emp.id, mentor=mentor, start_date=start or emp.hire_date or date.today(), scores={})
    for stage, items in tpl.items():
        for title in items:
            plan.items.append(OnboardingItem(stage=int(stage), title=title))
    db.add(plan)
    db.flush()
    audit(db, scope, "onboarding_create", f"employee:{emp.id}", mentor=mentor)
    return plan


def progress(plan: OnboardingPlan, today: date | None = None) -> dict:
    today = today or date.today()
    day = (today - plan.start_date).days + 1
    stage = stage_for_day(day)
    due = [i for i in plan.items if i.stage <= stage]
    done = [i for i in due if i.done]
    pct = round(100 * len(done) / len(due), 0) if due else 0.0
    return {"day": day, "stage": stage, "progress_pct": pct, "light": light(pct), "due": len(due), "done": len(done)}


def plan_card(plan: OnboardingPlan, today: date | None = None) -> dict:
    p = progress(plan, today)
    return {"plan_id": plan.id, "employee_id": plan.employee_id, "full_name": plan.employee.full_name,
            "position": plan.employee.position.title if plan.employee.position else None,
            "branch": plan.employee.branch.name if plan.employee.branch else None,
            "start_date": plan.start_date.isoformat(), "mentor": plan.mentor or None, **p,
            "scores": {k: {"score": v, "label": score_label(v)} for k, v in (plan.scores or {}).items()},
            "items": [{"id": i.id, "stage": i.stage, "title": i.title, "done": i.done} for i in plan.items],
            "updated_at": plan.updated_at.isoformat(timespec="minutes") if plan.updated_at else None}


def plans_in_scope(db: Session, scope: Scope) -> list[OnboardingPlan]:
    q = select(OnboardingPlan).join(Employee).where(Employee.status != "fired")
    if scope.branch_ids is not None:
        q = q.where(Employee.branch_id.in_(scope.branch_ids or {-1}))
    return list(db.scalars(q))


def status(db: Session, scope: Scope, today: date | None = None) -> dict:
    cards = [plan_card(p, today) for p in plans_in_scope(db, scope)]
    cards = [c for c in cards if c["day"] <= 120]
    return {"total": len(cards), "behind": sum(c["light"] == "red" for c in cards),
            "no_mentor": sum(not c["mentor"] for c in cards),
            "no_test": sum(not c["scores"] for c in cards if c["day"] > 25),
            "plans": sorted(cards, key=lambda c: c["progress_pct"])}


def my_plan(db: Session, scope: Scope) -> dict | None:
    """Self only — enforced in code (closes the 'ask for a colleague's plan' hole)."""
    if not scope.employee_id:
        return None
    p = db.scalar(select(OnboardingPlan).where(OnboardingPlan.employee_id == scope.employee_id))
    return plan_card(p) if p else None


def mark_item(db: Session, scope: Scope, item_id: int, done: bool = True) -> OnboardingItem:
    item = db.get(OnboardingItem, item_id)
    if not item:
        raise ValueError("Item not found")
    plan = db.get(OnboardingPlan, item.plan_id)
    if not scope.allows_branch(plan.employee.branch_id):
        raise NotAllowed("Not your branch")
    if scope.role in ("employee", "guest"):
        raise NotAllowed("Only a manager or HR marks items")
    item.done, item.done_at, item.done_by = done, datetime.now() if done else None, scope.actor if done else None
    plan.updated_at = datetime.now()
    audit(db, scope, "onboarding_item", f"item:{item.id}", done=done)
    return item


def record_score(db: Session, scope: Scope, plan: OnboardingPlan, score: int, stage: int | None = None) -> dict:
    if not 0 <= score <= 100:
        raise ValueError("Score must be 0..100")
    if not scope.allows_branch(plan.employee.branch_id):
        raise NotAllowed("Not your branch")
    stage = stage or progress(plan)["stage"]
    plan.scores = {**(plan.scores or {}), str(stage): score}
    plan.updated_at = datetime.now()
    audit(db, scope, "onboarding_score", f"plan:{plan.id}", stage=stage, score=score)
    return {"stage": stage, "score": score, "label": score_label(score)}
