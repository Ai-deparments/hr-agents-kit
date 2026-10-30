"""Hiring after the interview, all in conversation (no buttons): interview slots offered and picked by number,
reminders, a job offer the candidate accepts in words -> employee card (probation) + onboarding course."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import cfg
from ..models import Candidate, CandidateStep, Employee, InterviewSlot, Outbox, Position
from ..rbac import Scope, audit

ACCEPT_RE = re.compile(r"^(qabul qilaman|qabul|roziman|ha|xo'p|mayli|принимаю|согласен|согласна|да|accept)(\W|$)")
DECLINE_RE = re.compile(r"^(yo'?q|rad etaman|kerak emas|отказываюсь|нет|не согласен|decline)(\W|$)")


def _fmt(dt: datetime) -> str:
    return dt.strftime("%d.%m %H:%M")


def free_slots(db: Session, vacancy_id: int | None = None) -> list[InterviewSlot]:
    q = select(InterviewSlot).where(InterviewSlot.status == "free", InterviewSlot.starts_at > datetime.now())
    rows = list(db.scalars(q.order_by(InterviewSlot.starts_at)))
    return [s for s in rows if s.vacancy_id in (None, vacancy_id)]


def _close_open(db: Session, cand: Candidate, kind: str) -> None:
    for st in db.scalars(select(CandidateStep).where(CandidateStep.candidate_id == cand.id, CandidateStep.kind == kind,
                                                     CandidateStep.status == "open")):
        st.status = "cancelled"


def invite(db: Session, scope: Scope, cand: Candidate, slot_ids: list[int] | None = None) -> dict:
    """Offer free slots to the candidate in Telegram; they answer with a number."""
    if not cand.telegram_id:
        raise ValueError("Nomzodning Telegram'i yo'q · у кандидата нет Telegram")
    slots = [s for s in free_slots(db, cand.vacancy_id) if not slot_ids or s.id in slot_ids][:8]
    if not slots:
        raise ValueError("Bo'sh vaqt yo'q — avval suhbat vaqtlarini qo'shing · нет свободных слотов")
    _close_open(db, cand, "slots")
    db.add(CandidateStep(candidate_id=cand.id, kind="slots", data={"ids": [s.id for s in slots]}, created_by=scope.actor))
    lines = "\n".join(f"{i}. {_fmt(s.starts_at)}" + (f" · {s.place}" if s.place else "") for i, s in enumerate(slots, 1))
    title = cand.vacancy.title if cand.vacancy else ""
    db.add(Outbox(telegram_id=cand.telegram_id, text=f"Assalomu alaykum! {cfg('company.name', '')} — {title} bo'yicha suhbatga taklif qilamiz.\n\n"
                                                     f"{lines}\n\nQulay vaqt raqamini yozing."))
    audit(db, scope, "interview_invite", f"candidate:{cand.id}", slots=[s.id for s in slots])
    return {"offered": len(slots)}


def open_step(db: Session, tg_id: int) -> CandidateStep | None:
    return db.scalar(select(CandidateStep).join(Candidate).where(Candidate.telegram_id == tg_id, CandidateStep.status == "open")
                     .order_by(CandidateStep.id.desc()))


def answer(db: Session, step: CandidateStep, text: str) -> tuple[str, list[tuple[int, str]]]:
    """Candidate's reply. Returns (reply to the candidate, [(hr_tg_id, notice)] for HR)."""
    cand, low = step.candidate, text.strip().lower()
    hr_ids = sorted(_hr_ids())
    if step.kind == "slots":
        ids = step.data.get("ids", [])
        m = re.match(r"^\s*(\d{1,2})\b", low)
        if not m or not 1 <= int(m.group(1)) <= len(ids):
            return f"1 dan {len(ids)} gacha raqam yozing.", []
        slot = db.get(InterviewSlot, ids[int(m.group(1)) - 1])
        if not slot or slot.status != "free":
            return "Bu vaqt band bo'lib qoldi — boshqa raqamni yozing.", []
        slot.status, slot.candidate_id = "booked", cand.id
        step.status, step.answered_at = "done", datetime.now()
        where = f"\n📍 {slot.place}" if slot.place else ""
        return (f"✅ Suhbat: {_fmt(slot.starts_at)}{where}\nKechiksangiz, shu yerga yozing.",
                [(i, f"🗓 Suhbat band qilindi: {cand.full_name} — {_fmt(slot.starts_at)}") for i in hr_ids])
    # offer
    if ACCEPT_RE.search(low):
        step.status, step.answered_at = "done", datetime.now()
        emp = _hire(db, cand, step.data)
        return ("🎉 Tabriklaymiz! Taklif qabul qilindi. Birinchi ish kuni haqida HR siz bilan bog'lanadi.",
                [(i, f"✅ {cand.full_name} taklifni qabul qildi → xodim kartasi #{emp.id} ochildi (sinov muddati).") for i in hr_ids])
    if DECLINE_RE.search(low):
        step.status, step.answered_at = "declined", datetime.now()
        return ("Tushunarli, javobingiz uchun rahmat.", [(i, f"✖️ {cand.full_name} taklifni rad etdi.") for i in hr_ids])
    return "Taklifni qabul qilsangiz «qabul qilaman», bo'lmasa «yo'q» deb yozing.", []


def _hr_ids() -> set[int]:
    from ..config import settings
    s = settings()
    return s.owner_ids | s.hr_head_ids


def offer(db: Session, scope: Scope, cand: Candidate, position_id: int | None, salary_text: str, start: date,
          branch_id: int | None, note: str = "") -> dict:
    """Offer text from HR's own values only (never invented). Accepting it is the candidate's decision; hiring is done by
    the system only after HR sent the offer — a human action."""
    if not cand.telegram_id:
        raise ValueError("Nomzodning Telegram'i yo'q · у кандидата нет Telegram")
    pos = db.get(Position, position_id) if position_id else None
    title = pos.title if pos else (cand.vacancy.title if cand.vacancy else "")
    text = (f"📄 Ish taklifi — {cfg('company.name', '')}\n\nLavozim: {title}\nMaosh: {salary_text}\n"
            f"Ish boshlanishi: {start:%d.%m.%Y}" + (f"\n{note}" if note else "") +
            "\n\nQabul qilsangiz «qabul qilaman» deb yozing.")
    _close_open(db, cand, "offer")
    db.add(CandidateStep(candidate_id=cand.id, kind="offer", created_by=scope.actor, data={
        "position_id": pos.id if pos else None, "salary_text": salary_text, "start": start.isoformat(),
        "branch_id": branch_id or (cand.vacancy.branch_id if cand.vacancy else None), "text": text}))
    db.add(Outbox(telegram_id=cand.telegram_id, text=text))
    audit(db, scope, "offer_sent", f"candidate:{cand.id}", salary=salary_text, start=start.isoformat())
    return {"sent": True, "text": text}


def _hire(db: Session, cand: Candidate, data: dict) -> Employee:
    e = db.scalar(select(Employee).where(Employee.telegram_id == cand.telegram_id))
    if not e:
        e = Employee(full_name=cand.full_name, phone=cand.phone, telegram_id=cand.telegram_id, status="probation",
                     branch_id=data.get("branch_id"), position_id=data.get("position_id"),
                     hire_date=date.fromisoformat(data["start"]) if data.get("start") else date.today(),
                     bot_functions=["helpdesk", "onboarding"])
        db.add(e)
        db.flush()
    cand.status, cand.decided_at = "hired", datetime.now()
    from . import onboarding_media
    onboarding_media.auto_assign(db, Scope("system:offer", "owner", None, False), e)
    audit(db, None, "offer_accepted", f"candidate:{cand.id}", employee_id=e.id)
    return e


def remind(db: Session, now: datetime | None = None) -> list[tuple[int, str]]:
    """Interview reminders ~2 h before: to the candidate and to HR."""
    now = now or datetime.now()
    out = []
    for s in db.scalars(select(InterviewSlot).where(InterviewSlot.status == "booked", InterviewSlot.reminded.is_(False),
                                                    InterviewSlot.starts_at <= now + timedelta(hours=2),
                                                    InterviewSlot.starts_at > now)):
        c = db.get(Candidate, s.candidate_id)
        if c and c.telegram_id:
            out.append((c.telegram_id, f"⏰ Eslatma: suhbat {_fmt(s.starts_at)}" + (f"\n📍 {s.place}" if s.place else "")))
        out += [(i, f"⏰ {_fmt(s.starts_at)} — suhbat: {c.full_name if c else '—'} ({s.interviewer or 'HR'})") for i in _hr_ids()]
        s.reminded = True
    return out
