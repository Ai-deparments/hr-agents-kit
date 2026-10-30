"""Discipline rules (warnings -> fines). Rules are listed for HR, edited by admins only, never added or deleted here."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require
from ..db import get_db
from ..models import DisciplineRule, Employee
from ..rbac import Scope
from ..services import discipline

router = APIRouter(prefix="/api/discipline")


@router.get("/rules")
def rules(scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    return {"can_edit": "*" in scope.perms, "windows": list(discipline.WINDOWS),
            "rules": [discipline.rule_dict(r) for r in db.scalars(select(DisciplineRule).order_by(DisciplineRule.id))]}


class RuleIn(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=160)
    text: str | None = Field(default=None, max_length=4000)
    window: str | None = None
    warnings_before_fine: int | None = Field(default=None, ge=0, le=20)
    fine_amount: int | None = Field(default=None, ge=0, le=discipline.MAX_AMOUNT)
    extra_amount: int | None = Field(default=None, ge=0, le=discipline.MAX_AMOUNT)
    note: str | None = Field(default=None, max_length=300)
    starts_on: date | None = None


@router.patch("/rules/{rid}")
def rule_update(rid: int, body: RuleIn, scope: Scope = Depends(require("*")), db: Session = Depends(get_db)):
    r = db.get(DisciplineRule, rid)
    if not r:
        raise HTTPException(404, "Not found")
    try:
        discipline.update_rule(db, scope, r, body.model_dump(exclude_unset=True))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return discipline.rule_dict(r)


class ApplyIn(BaseModel):
    employee_id: int
    rule_id: int
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    reason: str = Field(min_length=3, max_length=300)


@router.post("/apply")
def apply(body: ApplyIn, scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    if not (scope.can("payroll.write") or scope.can("hr.write")):
        raise HTTPException(403, "No right to add entries")
    e, r = db.get(Employee, body.employee_id), db.get(DisciplineRule, body.rule_id)
    if not e or not scope.allows_branch(e.branch_id) or not r:
        raise HTTPException(404, "Not found")
    try:
        case = discipline.apply_rule(db, scope, e, r, body.month, body.reason)
    except PermissionError as x:
        raise HTTPException(403, str(x))
    except ValueError as x:
        raise HTTPException(409 if "blocked" in str(x) else 400, str(x))
    db.commit()
    return discipline.case_dict(case, None, scope.payroll)


@router.get("/cases")
def cases(month: str | None = None, scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    return discipline.cases(db, scope, month or date.today().strftime("%Y-%m"))
