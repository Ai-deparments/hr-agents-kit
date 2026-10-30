"""Interview slots, invites and job offers (candidate answers in the bot by words)."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require
from ..db import get_db
from ..models import Candidate, CandidateStep, InterviewSlot
from ..rbac import Scope, audit
from ..services import hiring

router = APIRouter(prefix="/api")


def _slot_row(s: InterviewSlot) -> dict:
    return {"id": s.id, "starts_at": s.starts_at, "minutes": s.minutes, "place": s.place, "interviewer": s.interviewer,
            "status": s.status, "vacancy_id": s.vacancy_id, "candidate_id": s.candidate_id,
            "candidate": s.candidate_id and _cand_name(s)}


def _cand_name(s: InterviewSlot) -> str | None:
    from sqlalchemy.orm import object_session
    c = object_session(s).get(Candidate, s.candidate_id)
    return c.full_name if c else None


def _slot_allowed(db: Session, scope: Scope, s: InterviewSlot) -> bool:
    """A branch-limited recruiter sees / cancels only slots of their branches' vacancies (or general slots)."""
    from ..models import Vacancy
    v = db.get(Vacancy, s.vacancy_id) if s.vacancy_id else None
    return not v or not v.branch_id or scope.allows_branch(v.branch_id)


@router.get("/slots")
def slots(scope: Scope = Depends(require("recruiting.read")), db: Session = Depends(get_db)):
    q = select(InterviewSlot).where(InterviewSlot.starts_at >= datetime.now().replace(hour=0, minute=0))
    return [_slot_row(s) for s in db.scalars(q.order_by(InterviewSlot.starts_at)) if _slot_allowed(db, scope, s)]


class SlotsIn(BaseModel):
    day: date
    times: list[str] = Field(min_length=1, max_length=20)  # ["10:00", "10:30"]
    minutes: int = Field(default=30, ge=10, le=240)
    place: str = Field(default="", max_length=300)
    interviewer: str = Field(default="", max_length=160)
    vacancy_id: int | None = None


@router.post("/slots")
def slots_add(body: SlotsIn, scope: Scope = Depends(require("recruiting")), db: Session = Depends(get_db)):
    made = []
    for t in body.times:
        try:
            hh, mm = map(int, t.strip().split(":"))
            at = datetime.combine(body.day, datetime.min.time()).replace(hour=hh, minute=mm)
        except ValueError:
            raise HTTPException(400, f"Bad time: {t}")
        if at <= datetime.now():
            raise HTTPException(400, f"Past time: {t}")
        s = InterviewSlot(starts_at=at, minutes=body.minutes, place=body.place, interviewer=body.interviewer,
                          vacancy_id=body.vacancy_id, created_by=scope.actor)
        db.add(s)
        made.append(s)
    if body.vacancy_id:
        from ..models import Vacancy
        v = db.get(Vacancy, body.vacancy_id)
        if not v or (v.branch_id and not scope.allows_branch(v.branch_id)):
            raise HTTPException(404, "Vacancy not found")
    db.flush()
    audit(db, scope, "slots_add", None, count=len(made), day=body.day.isoformat())
    db.commit()
    return [_slot_row(s) for s in made]


@router.delete("/slots/{sid}")
def slot_cancel(sid: int, scope: Scope = Depends(require("recruiting")), db: Session = Depends(get_db)):
    s = db.get(InterviewSlot, sid)
    if not s or s.status not in ("free", "booked") or not _slot_allowed(db, scope, s):
        raise HTTPException(404, "Not found")
    if s.status == "booked" and s.candidate_id:
        c = db.get(Candidate, s.candidate_id)
        if c and c.telegram_id:
            from ..models import Outbox
            db.add(Outbox(telegram_id=c.telegram_id, text=f"Suhbat ({s.starts_at:%d.%m %H:%M}) bekor qilindi. HR siz bilan bog'lanadi."))
        for st in db.scalars(select(CandidateStep).where(CandidateStep.candidate_id == s.candidate_id, CandidateStep.kind == "slots",
                                                         CandidateStep.status == "open")):
            st.status = "cancelled"  # a pending "move my interview" offer dies with the slot
    s.status = "cancelled"
    audit(db, scope, "slot_cancel", f"slot:{s.id}")
    db.commit()
    return {"ok": True}


def _cand(db: Session, scope: Scope, cid: int) -> Candidate:
    c = db.get(Candidate, cid)
    if not c or (c.vacancy and c.vacancy.branch_id and not scope.allows_branch(c.vacancy.branch_id)):
        raise HTTPException(404, "Not found")
    return c


@router.get("/candidates/{cid}/preview")
def preview(cid: int, action: str, scope: Scope = Depends(require("recruiting")), db: Session = Depends(get_db)):
    """The exact message the candidate would get for Invite / Reject. Nothing is saved or sent."""
    try:
        return hiring.preview(db, scope, _cand(db, scope, cid), action)
    except ValueError as e:
        raise HTTPException(400, str(e))


class InviteIn(BaseModel):
    slot_ids: list[int] = Field(default=[], max_length=50)
    expected_text: str | None = Field(default=None, max_length=4000)  # the previewed message; must still be exact


@router.post("/candidates/{cid}/invite")
def invite(cid: int, body: InviteIn, scope: Scope = Depends(require("recruiting")), db: Session = Depends(get_db)):
    try:
        out = hiring.invite(db, scope, _cand(db, scope, cid), body.slot_ids or None, body.expected_text)
    except ValueError as e:
        raise HTTPException(409 if "o'zgardi" in str(e) else 400, str(e))
    db.commit()
    return out


class RejectIn(BaseModel):
    expected_text: str | None = Field(default=None, max_length=4000)


@router.post("/candidates/{cid}/reject")
def reject(cid: int, body: RejectIn, scope: Scope = Depends(require("recruiting")), db: Session = Depends(get_db)):
    try:
        out = hiring.reject(db, scope, _cand(db, scope, cid), body.expected_text)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(409 if "changed" in str(e) else 400, str(e))
    db.commit()
    return out


class OfferIn(BaseModel):
    position_id: int | None = None
    branch_id: int | None = None
    salary_text: str = Field(min_length=1, max_length=200)
    start_date: date
    note: str = Field(default="", max_length=500)


@router.post("/candidates/{cid}/offer")
def offer(cid: int, body: OfferIn, scope: Scope = Depends(require("recruiting")), db: Session = Depends(get_db)):
    if body.branch_id and not scope.allows_branch(body.branch_id):
        raise HTTPException(403, "Not your branch")
    try:
        out = hiring.offer(db, scope, _cand(db, scope, cid), body.position_id, body.salary_text, body.start_date,
                           body.branch_id, body.note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return out


@router.get("/candidates/{cid}/steps")
def steps(cid: int, scope: Scope = Depends(require("recruiting.read")), db: Session = Depends(get_db)):
    c = _cand(db, scope, cid)
    booked = db.scalar(select(InterviewSlot).where(InterviewSlot.candidate_id == c.id, InterviewSlot.status == "booked"))
    return {"telegram": c.telegram_id is not None,
            "interview": _slot_row(booked) if booked else None,
            "steps": [{"id": s.id, "kind": s.kind, "status": s.status, "created_at": s.created_at, "answered_at": s.answered_at,
                       "text": s.data.get("text")} for s in db.scalars(select(CandidateStep).where(CandidateStep.candidate_id == c.id)
                                                                         .order_by(CandidateStep.id.desc()))]}
