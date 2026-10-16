from pathlib import Path

import pytest
import yaml

from app.agents.registry import route
from app.agents.runtime import refusal, run_agent
from app.rbac import scope_for_telegram
from app.services import recruiting

G = yaml.safe_load((Path(__file__).parents[1] / "evals" / "golden.yaml").read_text("utf-8"))


@pytest.mark.parametrize("text,agent", G["routing"])
def test_routing(text, agent):
    assert route(text) == agent


@pytest.mark.parametrize("tg,agent,text", G["refusals"])
def test_refusals(db, tg, agent, text):
    assert run_agent(db, agent, scope_for_telegram(db, tg), text, f"golden:{tg}") == refusal(agent)


@pytest.mark.parametrize("tg,agent,text,expect", G["allowed"])
def test_allowed(db, tg, agent, text, expect):
    ans = run_agent(db, agent, scope_for_telegram(db, tg), text, f"golden:{tg}")
    assert expect in ans and ans != refusal(agent)


@pytest.mark.parametrize("q", G["banned_interview_questions"])
def test_banned_questions(q):
    assert recruiting.find_banned(q)


@pytest.mark.parametrize("q", G["allowed_interview_questions"])
def test_allowed_questions(q):
    assert not recruiting.find_banned(q)
