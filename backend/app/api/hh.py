"""Recruiter: search hh.uz résumés and take a résumé into the candidate pipeline."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require
from ..db import get_db
from ..models import Candidate, Vacancy
from ..rbac import Scope, audit
from ..services import hh

router = APIRouter(prefix="/api/hh")


@router.get("/status")
def status(scope: Scope = Depends(require("hh.search"))):
    return hh.status()


@router.get("/search")
def search(text: str, area: str = "uz", experience: str = "", salary_to: int | None = None, page: int = 0,
           scope: Scope = Depends(require("hh.search")), db: Session = Depends(get_db)):
    try:
        out = hh.search(text, area, experience, salary_to, page)
    except hh.HhError as e:
        raise HTTPException(400, str(e))
    audit(db, scope, "hh_search", None, text=text[:100], area=area, found=out["found"])
    db.commit()
    taken = {c.breakdown.get("hh_id") for c in db.scalars(select(Candidate).where(Candidate.source == "hh")) if c.breakdown}
    for it in out["items"]:
        it["taken"] = it["id"] in taken
    return out


class TakeIn(BaseModel):
    hh_id: str = Field(min_length=1, max_length=40)
    title: str = Field(max_length=160)
    name: str | None = Field(default=None, max_length=160)
    vacancy_id: int | None = None
    note: str = Field(default="", max_length=500)
    url: str | None = Field(default=None, max_length=300)


@router.post("/take")
def take(body: TakeIn, scope: Scope = Depends(require("hh.search")), db: Session = Depends(get_db)):
    """Adds the résumé to candidates as 'new' (no contact bought; HR opens contacts on hh.uz)."""
    if body.vacancy_id:
        v = db.get(Vacancy, body.vacancy_id)
        if not v or (v.branch_id and not scope.allows_branch(v.branch_id)):
            raise HTTPException(404, "Vacancy not found")
    for c in db.scalars(select(Candidate).where(Candidate.source == "hh")):
        if (c.breakdown or {}).get("hh_id") == body.hh_id:
            raise HTTPException(409, "Already in candidates")
    host = (urlparse(body.url).hostname or "") if body.url else ""
    url = body.url if body.url and body.url.startswith("https://") and host in ("hh.uz", "hh.ru", "api.hh.ru") else None
    c = Candidate(vacancy_id=body.vacancy_id, full_name=(body.name or f"hh: {body.title}")[:160], source="hh",
                  answers=[{"q": "hh.uz", "a": f"{body.title}. {body.note}".strip()}],
                  breakdown={"hh_id": body.hh_id, "hh_url": url}, created_at=datetime.now())
    db.add(c)
    db.flush()
    audit(db, scope, "hh_take", f"candidate:{c.id}", hh_id=body.hh_id)
    db.commit()
    return {"id": c.id}
