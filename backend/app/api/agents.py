from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..agents.registry import AGENTS
from ..agents.runtime import llm_enabled, run_agent
from ..auth import panel_scope
from ..config import settings
from ..db import get_db
from ..rbac import Scope

router = APIRouter(prefix="/api/agents")


@router.get("")
def list_agents(scope: Scope = Depends(panel_scope)):
    return {"llm": llm_enabled(), "agents": [{"name": a.name, "title": a.title, "min_role": a.min_role,
                                              "commands": list(a.commands)} for a in AGENTS.values()]}


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


def _panel_as_bot(scope: Scope) -> Scope:
    """Panel users talk to agents with an equivalent bot role and the SAME branch scope."""
    role = "owner" if scope.role in ("admin", "executive") else "hr_head" if scope.role in ("hr_manager", "payroll", "recruiter") else "manager"
    return Scope(scope.actor, role, scope.branch_ids, scope.payroll, None, scope.perms)


@router.post("/{agent}/chat")
def chat(agent: str, body: ChatIn, scope: Scope = Depends(panel_scope), db: Session = Depends(get_db)):
    if agent not in AGENTS:
        raise HTTPException(404, "Unknown agent")
    if agent == "suhayl":
        raise HTTPException(400, "Suhayl talks to employees only (self data). Use Telegram.")
    return {"agent": agent, "answer": run_agent(db, agent, _panel_as_bot(scope), body.text, user_key=scope.actor)}


@router.post("/{agent}/ask")
def ask(agent: str, body: ChatIn, x_api_key: str = Header(""), db: Session = Depends(get_db)):
    """Internal API for other systems (e.g. a CEO agent). Acts as HR head, never as owner."""
    key = settings().agent_api_key
    if not key or x_api_key != key:
        raise HTTPException(401, "Bad API key")
    if agent not in AGENTS:
        raise HTTPException(404, "Unknown agent")
    scope = Scope("agent:external", "hr_head", None, payroll=False)
    return {"agent": agent, "answer": run_agent(db, agent, scope, body.text, user_key="external")}
