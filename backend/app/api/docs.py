"""HR document templates (edit in the panel) and issued documents as PDF."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require
from ..db import get_db
from ..models import DocTemplate, Employee, HrDoc
from ..rbac import Scope, audit
from ..services import docgen

router = APIRouter(prefix="/api/hr-docs")


def _tpl_row(t: DocTemplate) -> dict:
    return {"id": t.id, "code": t.code, "title": t.title, "body": t.body, "active": t.active, "fields": docgen.fields_of(t.body)}


def _doc_row(d: HrDoc) -> dict:
    return {"id": d.id, "title": d.title, "number": d.number, "template_code": d.template_code, "employee_id": d.employee_id,
            "employee": d.employee.full_name if d.employee else None, "missing": d.missing, "created_at": d.created_at,
            "created_by": d.created_by, "body": d.body}


@router.get("/templates")
def templates(scope: Scope = Depends(require("documents")), db: Session = Depends(get_db)):
    docgen.ensure_templates(db)
    db.commit()
    return [_tpl_row(t) for t in db.scalars(select(DocTemplate).order_by(DocTemplate.id))]


class TplIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    body: str = Field(min_length=5, max_length=20000)
    active: bool = True
    code: str | None = Field(default=None, pattern=r"^[a-z_]{3,40}$")


@router.post("/templates")
def tpl_create(body: TplIn, scope: Scope = Depends(require("documents")), db: Session = Depends(get_db)):
    if not body.code or db.scalar(select(DocTemplate).where(DocTemplate.code == body.code)):
        raise HTTPException(400, "Code is empty or taken")
    t = DocTemplate(code=body.code, title=body.title, body=body.body, active=body.active, updated_by=scope.actor)
    db.add(t)
    db.flush()
    audit(db, scope, "doc_template_create", f"doc_template:{t.id}")
    db.commit()
    return _tpl_row(t)


@router.patch("/templates/{tid}")
def tpl_update(tid: int, body: TplIn, scope: Scope = Depends(require("documents")), db: Session = Depends(get_db)):
    t = db.get(DocTemplate, tid)
    if not t:
        raise HTTPException(404, "Not found")
    t.title, t.body, t.active, t.updated_by = body.title, body.body, body.active, scope.actor
    audit(db, scope, "doc_template_update", f"doc_template:{t.id}")
    db.commit()
    return _tpl_row(t)


class IssueIn(BaseModel):
    template_id: int
    employee_id: int | None = None
    extra: dict[str, str] = {}


def _emp(db: Session, scope: Scope, eid: int | None) -> Employee | None:
    if eid is None:
        return None
    e = db.get(Employee, eid)
    if not e or (e.branch_id and not scope.allows_branch(e.branch_id)):
        raise HTTPException(404, "Employee not found")
    return e


@router.post("")
def issue(body: IssueIn, scope: Scope = Depends(require("documents")), db: Session = Depends(get_db)):
    t = db.get(DocTemplate, body.template_id)
    if not t or not t.active:
        raise HTTPException(404, "Template not found")
    if len(body.extra) > 30:
        raise HTTPException(400, "Too many fields")
    d = docgen.issue(db, scope, t, _emp(db, scope, body.employee_id), body.extra)
    db.commit()
    return _doc_row(d)


@router.get("")
def issued(employee_id: int | None = None, scope: Scope = Depends(require("documents")), db: Session = Depends(get_db)):
    q = select(HrDoc).order_by(HrDoc.id.desc()).limit(200)
    if employee_id:
        q = q.where(HrDoc.employee_id == employee_id)
    return [_doc_row(d) for d in db.scalars(q)
            if not d.employee or not d.employee.branch_id or scope.allows_branch(d.employee.branch_id)]


@router.get("/{did}/pdf")
def download(did: int, scope: Scope = Depends(require("documents")), db: Session = Depends(get_db)):
    d = db.get(HrDoc, did)
    if not d or (d.employee and d.employee.branch_id and not scope.allows_branch(d.employee.branch_id)):
        raise HTTPException(404, "Not found")
    return Response(docgen.pdf(d), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{d.number}.pdf"'})
