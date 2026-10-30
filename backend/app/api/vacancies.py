"""Vacancy editor for the web + the agent: AI draft from a brief, edit, AI rewrite with comment, versions, publish,
close, templates; and the public /jobs feed (no login)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require
from ..config import cfg
from ..db import get_db
from ..models import Vacancy, VacancyRevision
from ..rbac import Scope
from ..services import recruiting, vacancies

router = APIRouter(prefix="/api/vacancies")
public = APIRouter(prefix="/api/public")


def _get(db: Session, scope: Scope, vid: int) -> Vacancy:
    v = db.get(Vacancy, vid)
    if not v or (v.branch_id and not scope.allows_branch(v.branch_id)):
        raise HTTPException(404, "Not found")
    return v


def _row(db: Session, v: Vacancy, revisions: bool = False) -> dict:
    out = {"id": v.id, "title": v.title, "branch_id": v.branch_id, "branch": v.branch.name if v.branch else None,
           "status": v.status, "salary_text": v.salary_text, "schedule_text": v.schedule_text, "intro": v.intro,
           "duties": v.duties, "requirements": v.requirements, "benefits": v.benefits, "ad_text": v.ad_text,
           "public": v.public, "is_template": v.is_template, "published": v.published or {}, "missing": vacancies.missing(v),
           "apply_url": recruiting.apply_url(v), "channel_configured": bool(cfg("recruiting.jobs_channel"))}
    if revisions:
        out["revisions"] = [{"id": r.id, "comment": r.comment, "author": r.author, "created_at": r.created_at}
                            for r in db.scalars(select(VacancyRevision).where(VacancyRevision.vacancy_id == v.id)
                                                .order_by(VacancyRevision.id.desc()))]
    return out


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ValueError as e:
        raise HTTPException(400, str(e))


class BriefIn(BaseModel):
    brief: str = Field(min_length=3, max_length=2000)
    branch_id: int | None = None


@router.post("/ai")
def ai_draft(body: BriefIn, scope: Scope = Depends(require("recruiting")), db: Session = Depends(get_db)):
    if body.branch_id and not scope.allows_branch(body.branch_id):
        raise HTTPException(403, "Not your branch")
    v = vacancies.from_brief(db, scope, body.brief, body.branch_id)
    db.commit()
    return _row(db, v, True)


@router.get("/{vid}")
def detail(vid: int, scope: Scope = Depends(require("recruiting.read")), db: Session = Depends(get_db)):
    return _row(db, _get(db, scope, vid), True)


class EditIn(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    branch_id: int | None = None
    salary_text: str | None = Field(default=None, max_length=200)
    schedule_text: str | None = Field(default=None, max_length=200)
    intro: str | None = Field(default=None, max_length=2000)
    duties: str | None = Field(default=None, max_length=3000)
    requirements: str | None = Field(default=None, max_length=3000)
    benefits: str | None = Field(default=None, max_length=3000)


@router.patch("/{vid}")
def edit(vid: int, body: EditIn, scope: Scope = Depends(require("recruiting")), db: Session = Depends(get_db)):
    v = _get(db, scope, vid)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("branch_id") and not scope.allows_branch(changes["branch_id"]):
        raise HTTPException(403, "Not your branch")
    if changes.get("title") is not None and not changes["title"].strip():
        raise HTTPException(400, "Title required")
    vacancies.update(db, scope, v, changes)
    db.commit()
    return _row(db, v, True)


class CommentIn(BaseModel):
    comment: str = Field(min_length=2, max_length=1000)


@router.post("/{vid}/rewrite")
def rewrite(vid: int, body: CommentIn, scope: Scope = Depends(require("recruiting")), db: Session = Depends(get_db)):
    v = _get(db, scope, vid)
    _guard(vacancies.rewrite, db, scope, v, body.comment)
    db.commit()
    return _row(db, v, True)


@router.post("/{vid}/revert/{rid}")
def revert(vid: int, rid: int, scope: Scope = Depends(require("recruiting")), db: Session = Depends(get_db)):
    v = _get(db, scope, vid)
    r = db.get(VacancyRevision, rid)
    if not r or r.vacancy_id != v.id:
        raise HTTPException(404, "Version not found")
    vacancies.revert(db, scope, v, r)
    db.commit()
    return _row(db, v, True)


class PublishIn(BaseModel):
    web: bool = True
    channel: bool = False


@router.post("/{vid}/publish")
def publish(vid: int, body: PublishIn, scope: Scope = Depends(require("recruiting")), db: Session = Depends(get_db)):
    v = _get(db, scope, vid)
    _guard(vacancies.publish, db, scope, v, body.web, body.channel)
    db.commit()
    return _row(db, v, True)


@router.post("/{vid}/close")
def close(vid: int, scope: Scope = Depends(require("recruiting")), db: Session = Depends(get_db)):
    v = _get(db, scope, vid)
    vacancies.close(db, scope, v)
    db.commit()
    return _row(db, v)


@router.post("/{vid}/duplicate")
def duplicate(vid: int, scope: Scope = Depends(require("recruiting")), db: Session = Depends(get_db)):
    n = vacancies.duplicate(db, scope, _get(db, scope, vid))
    db.commit()
    return _row(db, n, True)


class TemplateIn(BaseModel):
    is_template: bool


@router.post("/{vid}/template")
def template(vid: int, body: TemplateIn, scope: Scope = Depends(require("recruiting")), db: Session = Depends(get_db)):
    v = _get(db, scope, vid)
    v.is_template = body.is_template
    db.commit()
    return _row(db, v)


# ---------------- public jobs feed (no login): only open + public vacancies, no internal fields ----------------

def _public_row(v: Vacancy) -> dict:
    return {"id": v.id, "title": v.title, "city": (v.branch.city or v.branch.name) if v.branch else None,
            "schedule": v.schedule_text, "salary": v.salary_text, "text": v.ad_text, "apply_url": recruiting.apply_url(v),
            "opened_at": v.opened_at}


@public.get("/jobs")
def jobs(db: Session = Depends(get_db)):
    return {"company": cfg("company.name", ""),
            "jobs": [_public_row(v) for v in db.scalars(select(Vacancy).where(Vacancy.status == "open", Vacancy.public.is_(True))
                                                         .order_by(Vacancy.opened_at.desc()))]}


@public.get("/jobs/{vid}")
def job(vid: int, db: Session = Depends(get_db)):
    v = db.get(Vacancy, vid)
    if not v or v.status != "open" or not v.public:
        raise HTTPException(404, "Not found")
    return _public_row(v)
