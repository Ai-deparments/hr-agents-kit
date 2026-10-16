"""Rauf's own recruiter panel (/rauf in the web app) and Rauf's HR Mini App (/m/rauf in Telegram).
Hire / reject are set only by a person; candidate data is cut by branch scope."""
from __future__ import annotations

import os
from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import miniapp_scope, require
from ..config import cfg
from ..db import get_db
from ..models import AdDeal, Candidate, Vacancy
from ..rbac import Scope
from ..services import analytics, recruiting

router = APIRouter(prefix="/api/rauf")
mini = APIRouter(prefix="/api/miniapp/rauf")

STAGES = ["new", "shortlist", "hired", "rejected"]


def _cands(db: Session, scope: Scope, vacancy_id: int | None = None) -> list[Candidate]:
    q = select(Candidate).order_by(Candidate.created_at.desc())
    if vacancy_id:
        q = q.where(Candidate.vacancy_id == vacancy_id)
    return [c for c in db.scalars(q)
            if not (c.vacancy and c.vacancy.branch_id and not scope.allows_branch(c.vacancy.branch_id))]


def _vacs(db: Session, scope: Scope) -> list[Vacancy]:
    return [v for v in db.scalars(select(Vacancy).order_by(Vacancy.id.desc()))
            if not (v.branch_id and not scope.allows_branch(v.branch_id))]


def _row(c: Candidate) -> dict:
    return {"id": c.id, "full_name": c.full_name, "phone": c.phone, "vacancy_id": c.vacancy_id,
            "vacancy": c.vacancy.title if c.vacancy else None,
            "branch": c.vacancy.branch.name if c.vacancy and c.vacancy.branch else None,
            "score": c.score, "label": c.label, "status": c.status, "source": c.source,
            "breakdown": c.breakdown, "answers": c.answers, "created_at": c.created_at}


@router.get("/dashboard")
def dashboard(scope: Scope = Depends(require("recruiting.read")), db: Session = Depends(get_db)):
    cands, vacs = _cands(db, scope), _vacs(db, scope)
    sla = analytics.vacancies_sla(db, scope)
    scored = [c.score for c in cands if c.score is not None]
    closed = [v for v in vacs if v.status == "closed" and v.opened_at and v.closed_at]
    lights = Counter(v["light"] for v in sla)
    return {
        "open_vacancies": sum(v.status == "open" for v in vacs),
        "draft_vacancies": sum(v.status == "draft" for v in vacs),
        "candidates": len(cands),
        "funnel": {s: sum(c.status == s for c in cands) for s in STAGES},
        "by_source": dict(Counter(c.source for c in cands)),
        "avg_score": round(sum(scored) / len(scored)) if scored else None,
        "unscored": sum(c.score is None for c in cands),
        "avg_days_to_close": round(sum((v.closed_at - v.opened_at).days for v in closed) / len(closed)) if closed else None,
        "sla": {"green": lights["green"], "yellow": lights["yellow"], "red": lights["red"]},
        "vacancies": sla,
        "recent": [_row(c) for c in cands[:8]],
    }


@router.get("/pipeline")
def pipeline(vacancy_id: int | None = None, scope: Scope = Depends(require("recruiting.read")), db: Session = Depends(get_db)):
    cands = _cands(db, scope, vacancy_id)
    return {s: [_row(c) for c in cands if c.status == s] for s in STAGES}


@router.get("/archive")
def archive(q: str = "", scope: Scope = Depends(require("recruiting.read")), db: Session = Depends(get_db)):
    ql = q.lower().strip()
    cands = [c for c in _cands(db, scope) if c.status in ("hired", "rejected")
             and (not ql or ql in f"{c.full_name} {c.phone or ''} {c.vacancy.title if c.vacancy else ''}".lower())]
    vacs = [{"id": v.id, "title": v.title, "branch": v.branch.name if v.branch else None, "opened_at": v.opened_at,
             "closed_at": v.closed_at, "days": (v.closed_at - v.opened_at).days if v.opened_at and v.closed_at else None}
            for v in _vacs(db, scope) if v.status == "closed"]
    return {"candidates": [_row(c) for c in cands], "vacancies": vacs}


@router.get("/ads")
def ads(scope: Scope = Depends(require("recruiting.read")), db: Session = Depends(get_db)):
    deals = list(db.scalars(select(AdDeal).order_by(AdDeal.created_at.desc())))
    return {"confirm_above": cfg("ads.budget_confirm_above"),
            "deals": [{"id": d.id, "channel": d.channel, "subscribers": d.subscribers, "stage": d.stage, "budget": d.budget,
                       "price": d.price, "vacancy_id": d.vacancy_id, "post_at": d.post_at} for d in deals]}


@router.get("/integrations")
def integrations(scope: Scope = Depends(require("recruiting.read"))):
    """Only whether a key is set — values never leave the server."""
    def on(*names):
        return all(bool(os.getenv(n)) for n in names)
    return [
        {"name": "Telegram recruiter bot", "connected": on("BOT_TOKEN_RAUF") or on("BOT_TOKEN_HUB")},
        {"name": "Claude (interview scoring)", "connected": on("ANTHROPIC_API_KEY")},
        {"name": "hh.uz", "connected": on("HH_CLIENT_ID", "HH_CLIENT_SECRET"), "note": "connector on the roadmap"},
        {"name": "vacandi.uz", "connected": on("VACANDI_API_KEY"), "note": "connector on the roadmap"},
        {"name": "osonish.uz", "connected": on("OSONISH_BASE_URL"), "note": "connector on the roadmap"},
        {"name": "Voice (speech-to-text)", "connected": on("GROQ_API_KEY"), "note": "optional"},
        {"name": "Ads control bot", "connected": on("BOT_TOKEN_REKLAMA")},
    ]


class CloseIn(BaseModel):
    reason: str = ""


@router.post("/vacancies/{vid}/close")
def close_vacancy(vid: int, body: CloseIn, scope: Scope = Depends(require("recruiting")), db: Session = Depends(get_db)):
    v = db.get(Vacancy, vid)
    if not v or (v.branch_id and not scope.allows_branch(v.branch_id)):
        raise HTTPException(404, "Not found")
    v.status, v.closed_at = "closed", date.today()
    from ..rbac import audit
    audit(db, scope, "vacancy_close", f"vacancy:{v.id}", reason=body.reason)
    db.commit()
    return {"id": v.id, "status": v.status}


# ---------------- Rauf HR Mini App (Telegram) ----------------

def _hr(scope: Scope) -> Scope:
    if not scope.at_least("hr_head"):  # same rule as the bot: HR mode only for owner / HR-head Telegram IDs
        raise HTTPException(403, "HR mode only")
    return scope


@mini.get("/candidates")
def mini_candidates(status: str | None = None, scope: Scope = Depends(miniapp_scope), db: Session = Depends(get_db)):
    _hr(scope)
    rows = [_row(c) for c in _cands(db, scope) if not status or c.status == status]
    return {"counts": {s: sum(r["status"] == s for r in rows) for s in STAGES} if not status else None, "rows": rows[:100]}


class StatusIn(BaseModel):
    status: str


@mini.post("/candidates/{cid}/status")
def mini_status(cid: int, body: StatusIn, scope: Scope = Depends(miniapp_scope), db: Session = Depends(get_db)):
    _hr(scope)
    c = db.get(Candidate, cid)
    if not c:
        raise HTTPException(404, "Not found")
    try:
        recruiting.set_status(db, scope, c, body.status)  # a person pressing a button in Telegram
    except (ValueError, PermissionError) as e:
        raise HTTPException(400, str(e))
    db.commit()
    return {"id": c.id, "status": c.status}
