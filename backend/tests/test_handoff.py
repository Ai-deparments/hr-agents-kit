"""Hire -> onboarding handoff: waiting list, one-click start (employee + plan + course in one transaction), dismiss."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Candidate, Employee, OnboardingHandoff, OnboardingPlan, Vacancy
from app.rbac import Scope
from app.services import onboarding, recruiting, topic_reports

c = TestClient(app)
HR = Scope("user:hr", "hr_manager", None, False, None, {"onboarding", "hr.read", "hr.write", "recruiting"})


def _h(u="hr", p="demo12345"):
    return {"Authorization": f"Bearer {c.post('/api/auth/login', json={'username': u, 'password': p}).json()['token']}"}


def _hired(db, name, tg=None):
    v = db.scalar(select(Vacancy).where(Vacancy.position_code == "pharmacist"))
    cand = Candidate(vacancy_id=v.id, full_name=name, phone="+998900000001", telegram_id=tg, status="shortlist")
    db.add(cand)
    db.flush()
    recruiting.set_status(db, HR, cand, "hired")
    db.commit()
    return cand


def _handoff(db, cand):
    return db.scalar(select(OnboardingHandoff).where(OnboardingHandoff.candidate_id == cand.id))


def test_hired_candidate_waits_and_reports_count_only(db):
    cand = _hired(db, "Waiting Wanda")
    assert any(r["candidate_id"] == cand.id for r in onboarding.waiting(db, HR))
    assert onboarding.status(db, HR)["waiting"] >= 1
    md = topic_reports.onboarding_md(db, HR)
    assert "Ishga olingan, boshlash kutilmoqda: **" in md and "Waiting Wanda" not in md  # the group gets the count only
    assert c.get("/api/onboarding", headers=_h()).json()["waiting"] >= 1


def test_one_click_start_creates_employee_plan_and_course(db):
    cand = _hired(db, "Started Sam", tg=880001)
    h = _handoff(db, cand)
    r = c.post(f"/api/onboarding/waiting/{h.id}/start", json={"mentor": "Head"}, headers=_h())
    assert r.status_code == 200, r.text
    db.expire_all()
    emp = db.scalar(select(Employee).where(Employee.full_name == "Started Sam"))
    assert emp.status == "probation" and emp.telegram_id == 880001 and emp.position.code == "pharmacist"
    assert set(emp.bot_functions) == {"helpdesk", "onboarding"}
    plan = db.scalar(select(OnboardingPlan).where(OnboardingPlan.employee_id == emp.id))
    assert plan.items and plan.mentor == "Head"
    assert c.post(f"/api/onboarding/waiting/{h.id}/start", json={}, headers=_h()).status_code == 400  # only once
    assert all(x["candidate_id"] != cand.id for x in onboarding.waiting(db, HR))


def test_dismiss_needs_reason_and_rights(db):
    cand = _hired(db, "Dismissed Dan")
    h = _handoff(db, cand)
    assert c.post(f"/api/onboarding/waiting/{h.id}/dismiss", json={"reason": "x"}, headers=_h()).status_code == 422
    assert c.post(f"/api/onboarding/waiting/{h.id}/dismiss", json={"reason": "did not show up"}, headers=_h("regional")).status_code == 403
    r = c.post(f"/api/onboarding/waiting/{h.id}/dismiss", json={"reason": "did not show up"}, headers=_h())
    assert r.status_code == 200 and r.json()["status"] == "dismissed"


def test_agent_cannot_start_and_branch_scope(db):
    cand = _hired(db, "Scoped Sue")
    h = _handoff(db, cand)
    with pytest.raises(onboarding.NotAllowed):
        onboarding.start_from_handoff(db, Scope("agent:hr", "owner", None), h)
    other = Scope("user:x", "hr_manager", {-1}, False, None, {"onboarding"})
    assert all(x["candidate_id"] != cand.id for x in onboarding.waiting(db, other))
    with pytest.raises(onboarding.NotAllowed):
        onboarding.start_from_handoff(db, other, h)
    db.rollback()


def test_no_handoff_when_the_person_already_has_a_card(db):
    """An offer accepted in the bot already opened the card: marking 'hired' later adds nothing to the waiting list."""
    e = Employee(full_name="Offer Olim", telegram_id=880002, status="probation")
    db.add(e)
    db.commit()
    cand = _hired(db, "Offer Olim", tg=880002)
    assert _handoff(db, cand) is None
