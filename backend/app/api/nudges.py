"""Discipline reminders: HR reviews the weekly drafts, edits, sends or skips."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require
from ..db import get_db
from ..models import Nudge
from ..rbac import Scope, audit
from ..services import nudges

router = APIRouter(prefix="/api/nudges")


def _row(n: Nudge) -> dict:
    return {"id": n.id, "employee": n.employee.full_name, "week": n.week, "late_days": n.late_days, "late_min": n.late_min,
            "text": n.text, "status": n.status, "decided_by": n.decided_by}


@router.get("")
def listing(status: str = "draft", scope: Scope = Depends(require("broadcast")), db: Session = Depends(get_db)):
    rows = db.scalars(select(Nudge).where(Nudge.status == status).order_by(Nudge.late_days.desc()).limit(200))
    return [_row(n) for n in rows if not n.employee.branch_id or scope.allows_branch(n.employee.branch_id)]


@router.post("/draft")
def draft(scope: Scope = Depends(require("broadcast")), db: Session = Depends(get_db)):
    made = nudges.draft_week(db, scope)
    db.commit()
    return {"drafted": len(made)}


class EditIn(BaseModel):
    text: str = Field(min_length=5, max_length=2000)


def _get(db: Session, scope: Scope, nid: int) -> Nudge:
    n = db.get(Nudge, nid)
    if not n or n.status != "draft" or (n.employee.branch_id and not scope.allows_branch(n.employee.branch_id)):
        raise HTTPException(404, "Not found")
    return n


@router.patch("/{nid}")
def edit(nid: int, body: EditIn, scope: Scope = Depends(require("broadcast")), db: Session = Depends(get_db)):
    n = _get(db, scope, nid)
    n.text = body.text
    db.commit()
    return _row(n)


@router.post("/{nid}/skip")
def skip(nid: int, scope: Scope = Depends(require("broadcast")), db: Session = Depends(get_db)):
    n = _get(db, scope, nid)
    n.status, n.decided_by = "skipped", scope.actor
    audit(db, scope, "nudge_skip", f"nudge:{n.id}")
    db.commit()
    return {"ok": True}


class SendIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


class RuleIn(BaseModel):
    enabled: bool
    late_count: int = Field(default=3, ge=1, le=31)
    to: str = Field(default="owner", pattern="^(owner|owner_hr)$")


@router.get("/lateness-rule")
def lateness_rule(scope: Scope = Depends(require("attendance.write")), db: Session = Depends(get_db)):
    from ..services import discipline_alerts as da
    return {"rule": da.get(db), "over_limit": da.over_limit(db)}


@router.put("/lateness-rule")
def lateness_rule_save(body: RuleIn, scope: Scope = Depends(require("attendance.write")), db: Session = Depends(get_db)):
    from ..services import discipline_alerts as da
    rule = da.save(db, body.enabled, body.late_count, body.to)
    audit(db, scope, "lateness_alert_rule", None, **rule)
    db.commit()
    return {"rule": rule, "over_limit": da.over_limit(db)}


@router.post("/send")
def send(body: SendIn, scope: Scope = Depends(require("broadcast")), db: Session = Depends(get_db)):
    n = nudges.send(db, scope, body.ids)
    db.commit()
    return {"sent": n}
