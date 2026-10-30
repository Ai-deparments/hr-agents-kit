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
    return {"total": len(cards), "behind": sum(c["light"] == "red" for c in cards), "waiting": len(waiting(db, scope, today)),
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


# ---------------- hire -> onboarding handoff ----------------

def _handoff_branch(h) -> int | None:
    v = h.candidate.vacancy
    return v.branch_id if v else None


def waiting(db: Session, scope: Scope, today: date | None = None) -> list[dict]:
    """Hired candidates without an employee card yet (oldest first)."""
    from ..models import OnboardingHandoff
    today = today or date.today()
    out = []
    for h in db.scalars(select(OnboardingHandoff).where(OnboardingHandoff.status == "waiting").order_by(OnboardingHandoff.id)):
        c = h.candidate
        if c.status != "hired" or not scope.allows_branch(_handoff_branch(h)):
            continue
        v = c.vacancy
        out.append({"id": h.id, "candidate_id": c.id, "full_name": c.full_name, "phone": c.phone,
                    "vacancy": v.title if v else None, "branch_id": v.branch_id if v else None,
                    "branch": v.branch.name if v and v.branch else None, "position_code": v.position_code if v else None,
                    "since": h.created_at.date().isoformat(), "days_waiting": (today - h.created_at.date()).days})
    return out


def start_from_handoff(db: Session, scope: Scope, h, mentor: str | None = None, start: date | None = None,
                       branch_id: int | None = None, position_id: int | None = None) -> OnboardingPlan:
    """One click, one transaction: employee card (probation) + 30/60/90 plan from the position template + the course."""
    from ..models import Position
    from . import onboarding_media
    if scope.actor.startswith("agent:"):
        raise NotAllowed("Only a person starts onboarding")
    if h.status != "waiting" or h.candidate.status != "hired":
        raise ValueError("Already handled")
    c, v = h.candidate, h.candidate.vacancy
    branch_id = branch_id or (v.branch_id if v else None)
    if not branch_id:
        raise ValueError("Choose the branch")
    if not scope.allows_branch(branch_id) or not scope.allows_branch(_handoff_branch(h)):
        raise NotAllowed("Not your branch")
    if not position_id and v and v.position_code:
        position_id = db.scalar(select(Position.id).where(Position.code == v.position_code))
    tg = c.telegram_id if c.telegram_id and not db.scalar(select(Employee.id).where(Employee.telegram_id == c.telegram_id)) else None
    emp = Employee(full_name=c.full_name, phone=c.phone, telegram_id=tg, branch_id=branch_id, position_id=position_id,
                   hire_date=start or date.today(), status="probation", bot_functions=["helpdesk", "onboarding"] if tg else [])
    db.add(emp)
    db.flush()
    db.refresh(emp)  # loads the position for the template choice
    plan = create_plan(db, scope, emp, mentor, start)
    onboarding_media.auto_assign(db, scope, emp)
    h.status, h.employee_id, h.decided_by, h.decided_at = "started", emp.id, scope.actor, datetime.now()
    audit(db, scope, "onboarding_handoff_start", f"candidate:{c.id}", employee_id=emp.id)
    return plan


def dismiss_handoff(db: Session, scope: Scope, h, reason: str):
    if scope.actor.startswith("agent:"):
        raise NotAllowed("Only a person dismisses")
    if h.status != "waiting":
        raise ValueError("Already handled")
    if not scope.allows_branch(_handoff_branch(h)):
        raise NotAllowed("Not your branch")
    if len((reason or "").strip()) < 3:
        raise ValueError("Reason is required")
    h.status, h.reason, h.decided_by, h.decided_at = "dismissed", reason.strip()[:300], scope.actor, datetime.now()
    audit(db, scope, "onboarding_handoff_dismiss", f"candidate:{h.candidate_id}", reason=h.reason)
    return h
