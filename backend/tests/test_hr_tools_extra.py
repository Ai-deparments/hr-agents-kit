"""Tools added after the 60-question group test: slots, offer, new hires, attendance by department, onboarding today, hh."""
import json
from datetime import date, timedelta

from sqlalchemy import select

from app.agents.registry import AGENTS
from app.agents.tools import TOOLS, Ctx, execute, tools_for
from app.models import Candidate, Outbox
from app.rbac import Scope
from app.services import attendance as att

OWNER = Scope("tg:1", "owner", None, True)


def run(db, name, args=None):
    return json.loads(execute(Ctx(db, OWNER, "hr"), TOOLS[name], args or {}))


def test_slots_offer_and_lists(db, monkeypatch):
    day = (date.today() + timedelta(days=1)).isoformat()
    assert run(db, "interview_slots_add", {"day": day, "times": ["10:00", "11:00"], "place": "Ofis"})["added"]
    assert len([s for s in run(db, "interview_slots") if s["status"] == "free"]) >= 2
    assert "error" in run(db, "interview_slots_add", {"day": "2020-01-01", "times": ["10:00"]})
    c = Candidate(full_name="Offer Test", telegram_id=777555, source="bot")
    db.add(c)
    db.commit()
    out = run(db, "job_offer", {"candidate_id": c.id, "salary_text": "5 000 000 so'm", "start_date": day})
    assert out["sent"] and db.scalar(select(Outbox).where(Outbox.telegram_id == 777555))
    assert "employees" in run(db, "new_hires", {"days": 30})
    assert isinstance(run(db, "attendance_by_department", {"days": 3}), list)
    assert set(run(db, "onboarding_today")) >= {"talks_today", "not_viewed_2d", "on_probation"}
    monkeypatch.setenv("HH_DEMO", "1")
    monkeypatch.delenv("HH_TOKEN_FILE", raising=False)
    assert run(db, "hh_search", {"text": "frontend"})["items"]


def test_new_tools_are_hr_only_where_needed():
    emp = Scope("tg:9", "employee", {1}, False, 1)
    names = {t.name for t in tools_for(AGENTS["hr"].tools, emp)}
    assert not names & {"job_offer", "hh_search", "interview_slots_add"}


def test_late_counts_people_still_on_shift():
    assert att.was_late("on_shift", 13) and not att.was_late("on_shift", 0)
