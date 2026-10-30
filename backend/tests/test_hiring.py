"""Slots -> invite -> candidate answers a number -> offer -> 'qabul qilaman' -> employee on probation + onboarding."""
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.bots import main as bot
from app.main import app
from app.models import Candidate, Employee, InterviewSlot, Outbox

c = TestClient(app)


def _login(u, p):
    r = c.post("/api/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_full_hiring_flow(db):
    hr = _login("hr", "demo12345")
    cand = Candidate(full_name="Nodir Test", phone="+998901112244", telegram_id=888001, source="bot")
    db.add(cand)
    db.commit()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    made = c.post("/api/slots", headers=hr, json={"day": tomorrow, "times": ["10:00", "10:30"], "place": "Ofis, 2-qavat"}).json()
    assert len(made) == 2
    assert c.post("/api/slots", headers=hr, json={"day": "2020-01-01", "times": ["10:00"]}).status_code == 400
    assert c.post(f"/api/candidates/{cand.id}/invite", headers=hr, json={}).json()["offered"] >= 2
    assert "Qulay vaqt raqamini" in db.scalar(select(Outbox).where(Outbox.telegram_id == 888001)).text
    assert "raqam" in bot._candidate_answer(888001, "ertaga")          # not a number -> asks again
    ok = bot._candidate_answer(888001, "2")
    assert ok.startswith("✅ Suhbat")
    booked = db.scalar(select(InterviewSlot).where(InterviewSlot.candidate_id == cand.id))
    db.refresh(booked)
    assert booked.status == "booked"
    assert bot._candidate_answer(888001, "salom").startswith("✅ Suhbat")  # booked: the booking is repeated, not re-offered
    assert bot._candidate_answer(888002, "salom") is None              # not a candidate: not a hiring conversation
    pos = c.get("/api/dictionaries", headers=hr).json()["positions"][0]["id"]
    r = c.post(f"/api/candidates/{cand.id}/offer", headers=hr, json={"position_id": pos, "salary_text": "6 000 000 so'm",
                                                                   "start_date": tomorrow}).json()
    assert "6 000 000 so'm" in r["text"]
    assert bot._candidate_answer(888001, "Qabul qilaman!").startswith("🎉")
    e = db.scalar(select(Employee).where(Employee.telegram_id == 888001))
    assert e and e.status == "probation" and e.position_id == pos and e.hire_date.isoformat() == tomorrow
    db.refresh(cand)
    assert cand.status == "hired"
    steps = c.get(f"/api/candidates/{cand.id}/steps", headers=hr).json()
    assert steps["interview"]["status"] == "booked" and {s["status"] for s in steps["steps"]} == {"done"}
    assert c.post(f"/api/candidates/{cand.id}/invite", headers=_login("buh", "demo12345"), json={}).status_code == 403


def test_lang_by_text_and_last_draft(db):
    from app.models import Vacancy
    assert bot.detect_lang(501, "rekruter post tayorlab ber", "ru") == "uz"   # Russian Telegram, Uzbek text -> uz
    assert bot.detect_lang(501, "/start", "ru") == "uz"                        # remembered
    assert bot.detect_lang(501, "сделай отчёт", "uz") == "ru"
    assert bot.detect_lang(502, "/start", "ru") == "ru"                        # nothing written yet -> Telegram language
    v = Vacancy(title="Frontend", status="draft", created_by="tg:777123")
    db.add(v)
    db.commit()
    assert bot._last_draft(777123) == v.id and bot._last_draft(777124) is None


def test_exit_answer_survives_restart(db):
    from datetime import date as d
    from app.models import PulseSent
    e = Employee(full_name="Ketgan Xodim", telegram_id=990011, status="fired", fire_date=d.today())
    db.add(e)
    db.flush()
    db.add(PulseSent(employee_id=e.id, kind="exit", month=d.today().strftime("%Y-%m")))
    db.commit()
    assert bot._open_exit(990011) and not bot._open_exit(990012)
