"""Invite / Reject with the exact message preview, outbox at most once, free-text booking (model maps only to offered
slots), atomic booking, move / cancel by text, reminders the day before at 18:00 and 1 h before."""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.bots import main as bot
from app.main import app
from app.models import Candidate, CandidateStep, InterviewSlot, Outbox, Vacancy
from app.rbac import Scope
from app.services import hiring, llm, outbox

c = TestClient(app)
HR = Scope("user:hr", "hr_manager", None, False, None, {"recruiting"})


def _h(u="hr", p="demo12345"):
    return {"Authorization": f"Bearer {c.post('/api/auth/login', json={'username': u, 'password': p}).json()['token']}"}


@pytest.fixture
def setup(db):
    """A vacancy with 3 free slots in 3 days' time; every other free slot is retired so offers are predictable."""
    db.execute(update(InterviewSlot).where(InterviewSlot.status.in_(("free", "booked"))).values(status="cancelled"))
    v = Vacancy(title="Interview cashier", status="open")
    db.add(v)
    db.flush()
    day = datetime.combine(date.today() + timedelta(days=3), datetime.min.time())
    slots = [InterviewSlot(vacancy_id=v.id, starts_at=day.replace(hour=h, minute=m), place="Office")
             for h, m in ((10, 0), (10, 30), (11, 0))]
    db.add_all(slots)
    db.commit()
    return v, slots


def _cand(db, v, tg, name="Iroda Nomzod"):
    cand = Candidate(full_name=name, telegram_id=tg, vacancy_id=v.id, source="bot")
    db.add(cand)
    db.commit()
    return cand


def _msgs(db, tg):
    return [o.text for o in db.scalars(select(Outbox).where(Outbox.telegram_id == tg).order_by(Outbox.id))]


def test_preview_is_exactly_what_is_sent_and_sent_once(db, setup):
    v, slots = setup
    cand = _cand(db, v, 770001)
    p = c.get(f"/api/candidates/{cand.id}/preview?action=invite", headers=_h()).json()
    assert p["offered"] == [s.id for s in slots] and "Qulay vaqt raqamini" in p["text"]
    r = c.post(f"/api/candidates/{cand.id}/invite", headers=_h(), json={"expected_text": p["text"]})
    assert r.status_code == 200 and r.json()["queued"]
    again = c.post(f"/api/candidates/{cand.id}/invite", headers=_h(), json={"expected_text": p["text"]}).json()
    assert again["queued"] is False  # a double click queues nothing twice
    db.expire_all()
    assert _msgs(db, 770001) == [p["text"]]
    stale = c.post(f"/api/candidates/{cand.id}/invite", headers=_h(), json={"expected_text": p["text"] + "x"})
    assert stale.status_code == 409  # slots / text changed since the preview -> nothing sent
    assert c.get(f"/api/candidates/{cand.id}/preview?action=fire", headers=_h()).status_code == 400
    assert c.get(f"/api/candidates/{cand.id}/preview?action=invite", headers=_h("buh")).status_code == 403


def test_reject_preview_message_frees_slot_and_is_human_only(db, setup):
    v, slots = setup
    cand = _cand(db, v, 770002, "Rad Nomzod")
    hiring.invite(db, HR, cand)
    db.commit()
    assert bot._candidate_answer(770002, "1").startswith("✅")
    with pytest.raises(PermissionError):
        hiring.reject(db, Scope("agent:hr", "hr_head", None), cand)
    db.rollback()
    p = c.get(f"/api/candidates/{cand.id}/preview?action=reject", headers=_h()).json()
    r = c.post(f"/api/candidates/{cand.id}/reject", headers=_h(), json={"expected_text": p["text"]}).json()
    assert r["status"] == "rejected" and r["queued"]
    db.expire_all()
    assert _msgs(db, 770002)[-1] == p["text"] and "Rad Nomzod" in p["text"]
    assert db.get(InterviewSlot, slots[0].id).status == "free"  # the booked slot is free again
    assert c.post(f"/api/candidates/{cand.id}/reject", headers=_h(), json={}).status_code == 400
    assert bot._candidate_answer(770002, "salom") is None  # a rejected candidate is no longer in a hiring conversation


def test_free_text_time_and_model_maps_only_to_offered(db, setup, monkeypatch):
    v, slots = setup
    cand = _cand(db, v, 770003)
    hiring.invite(db, HR, cand)
    db.commit()
    d = slots[2].starts_at
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"action": "book", "slot_id": 999999})  # not offered
    assert "raqam" in bot._candidate_answer(770003, "qachon bo'lsa ham mayli")
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"action": "book", "slot_id": slots[1].id})
    assert bot._candidate_answer(770003, "ertalabki ikkinchi vaqt").startswith("✅")
    db.expire_all()
    assert db.get(InterviewSlot, slots[1].id).candidate_id == cand.id
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: None)
    # move by text: another time is offered, then a time written as text books it and frees the old slot
    assert "Boshqa vaqtni" in bot._candidate_answer(770003, "boshqa vaqt kerak")
    assert bot._candidate_answer(770003, f"{d:%d.%m} {d:%H:%M} bo'ladi").startswith("✅")
    db.expire_all()
    assert db.get(InterviewSlot, slots[2].id).candidate_id == cand.id and db.get(InterviewSlot, slots[1].id).status == "free"
    # cancel by text
    assert "bekor" in bot._candidate_answer(770003, "kechirasiz, kelolmayman")
    db.expire_all()
    assert db.get(InterviewSlot, slots[2].id).status == "free"
    assert bot._candidate_answer(770003, "salom") is None


def test_booking_is_atomic(db, setup):
    v, slots = setup
    a, b = _cand(db, v, 770004, "Birinchi"), _cand(db, v, 770005, "Ikkinchi")
    for x in (a, b):
        hiring.invite(db, HR, x)
    db.commit()
    assert hiring.book(db, slots[0].id, a.id) and not hiring.book(db, slots[0].id, b.id)
    db.commit()
    reply = bot._candidate_answer(770005, "1")  # number 1 in their message is the slot just taken
    assert reply.startswith("Bu vaqt band") and slots[1].starts_at.strftime("%H:%M") in reply
    assert bot._candidate_answer(770005, "1").startswith("✅")  # numbers now follow the new list (1 = 10:30)
    db.expire_all()
    assert db.get(InterviewSlot, slots[1].id).candidate_id == b.id
    db.expire_all()
    assert db.get(InterviewSlot, slots[0].id).candidate_id == a.id


def test_reminders_day_before_1800_and_hour_before_once(db, setup):
    v, slots = setup
    cand = _cand(db, v, 770006)
    s = slots[0]
    assert hiring.book(db, s.id, cand.id)
    db.execute(update(InterviewSlot).where(InterviewSlot.id == s.id).values(booked_at=s.starts_at - timedelta(days=2)))
    db.commit()
    eve = datetime.combine(s.starts_at.date() - timedelta(days=1), datetime.min.time()).replace(hour=18, minute=1)
    mine = lambda now: [t for tg, t in hiring.remind(db, now) if tg == 770006]  # noqa: E731
    assert mine(eve - timedelta(minutes=5)) == []
    day = [t for tg, t in hiring.remind(db, eve) if tg == 770006]
    assert len(day) == 1 and "ertaga" in day[0]
    assert mine(eve + timedelta(minutes=10)) == []  # at most once
    hour = [t for tg, t in hiring.remind(db, s.starts_at - timedelta(minutes=59)) if tg == 770006]
    assert len(hour) == 1 and "60 daqiqadan" in hour[0]
    assert mine(s.starts_at - timedelta(minutes=30)) == []
    db.commit()
    # booked after 18:00 the day before -> no "tomorrow" note
    late = _cand(db, v, 770007)
    assert hiring.book(db, slots[1].id, late.id)
    db.execute(update(InterviewSlot).where(InterviewSlot.id == slots[1].id).values(booked_at=eve + timedelta(hours=1)))
    db.commit()
    assert not [t for tg, t in hiring.remind(db, eve + timedelta(hours=2)) if tg == 770007]
    db.rollback()


def test_outbox_claim_is_at_most_once(db):
    o = outbox.queue(db, 770100, "hello once", dedupe="t:once")
    assert outbox.queue(db, 770100, "hello once", dedupe="t:once") is None
    db.commit()
    got = [x for x in outbox.claim(db, 500) if x.id == o.id]
    assert got and not [x for x in outbox.claim(db, 500) if x.id == o.id]  # a second worker gets nothing
    # the bot crashed before finishing: the row stays claimed and is never sent again
    db.expire_all()
    assert db.get(Outbox, o.id).claimed_at and db.get(Outbox, o.id).sent_at is None
    outbox.finish(db, got[0], True)
    assert db.get(Outbox, o.id).sent_at is not None


def test_agent_tool_invite_and_steps_endpoint(db, setup):
    v, _ = setup
    cand = _cand(db, v, 770008)
    from app.agents.tools import TOOLS, Ctx
    out = TOOLS["interview_invite"].fn(Ctx(db, Scope("tg:9999", "owner", None, True), "hr"), candidate_id=cand.id)
    db.commit()
    assert "error" not in out
    steps = c.get(f"/api/candidates/{cand.id}/steps", headers=_h()).json()
    assert steps["steps"][0]["kind"] == "slots" and steps["steps"][0]["status"] == "open"
    assert db.scalar(select(CandidateStep).where(CandidateStep.candidate_id == cand.id)).data["text"].startswith("Assalomu")
