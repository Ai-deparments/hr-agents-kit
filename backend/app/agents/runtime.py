"""Agent loop on the Claude API (official SDK, manual tool-use loop).
Offline mode (no credentials): slash-commands and keywords run tools deterministically."""
from __future__ import annotations

import json
import logging
import os
from datetime import date
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import cfg, settings
from ..models import ChatMessage
from ..rbac import Scope, audit
from .registry import AGENTS
from .tools import TOOLS, Ctx, execute, tools_for

log = logging.getLogger("agents")
PERSONAS = Path(__file__).parent / "personas"
MAX_STEPS = 8


def llm_enabled() -> bool:
    mode = os.getenv("LLM_MODE", "auto")
    if mode == "offline":
        return False
    if mode == "claude":
        return True
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


@lru_cache
def persona(agent: str) -> str:
    c = cfg("company", {})
    text = (PERSONAS / f"{agent}.md").read_text("utf-8-sig") + "\n\n" + (PERSONAS / "_shared.md").read_text("utf-8-sig")
    return (text.replace("{company}", c.get("name", "the company")).replace("{description}", c.get("description", ""))
            .replace("{currency}", c.get("currency", "UZS")))


def _history(db: Session, agent: str, user_key: str, n: int = 10) -> list[dict]:
    rows = list(db.scalars(select(ChatMessage).where(ChatMessage.agent == agent, ChatMessage.user_key == user_key)
                           .order_by(ChatMessage.id.desc()).limit(n)))[::-1]
    msgs = [{"role": r.role, "content": r.text} for r in rows]
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs


def _save(db: Session, agent: str, user_key: str, role: str, text: str, scope: Scope) -> None:
    branch = next(iter(scope.branch_ids), None) if scope.branch_ids else None
    db.add(ChatMessage(agent=agent, user_key=user_key, role=role, text=text[:8000], branch_id=branch))


def refusal(agent: str) -> str:
    return {"suhayl": "Your Telegram is not linked to an employee card. Send /id and give the number to HR."}.get(
        agent, "This assistant is for managers and HR only.")


def run_agent(db: Session, agent: str, scope: Scope, text: str, user_key: str, depth: int = 0) -> str:
    a = AGENTS.get(agent)
    if not a:
        return "Unknown agent"
    if not scope.at_least(a.min_role):
        audit(db, scope, "agent_refused", agent)
        return refusal(agent)
    ctx = Ctx(db=db, scope=scope, agent=agent, depth=depth)
    tools = tools_for(a.tools, scope)
    if not depth:
        audit(db, scope, "agent_message", agent, text=text[:500])
    cmd = text.strip().split()[0].split("@")[0].lower() if text.strip() else ""
    if cmd in a.commands or not llm_enabled():
        answer = offline_answer(ctx, a, tools, text)
    else:
        try:
            answer = claude_answer(ctx, a, tools, text, user_key)
        except Exception as e:  # network / API errors must not crash the bot
            log.exception("claude call failed")
            answer = "AI is busy right now, please try again in a minute. (" + type(e).__name__ + ")"
    if not depth:
        _save(db, agent, user_key, "user", text, scope)
        _save(db, agent, user_key, "assistant", answer, scope)
    db.commit()
    return answer


def claude_answer(ctx: Ctx, a, tools, text: str, user_key: str) -> str:
    import anthropic

    s = settings()
    client = anthropic.Anthropic()
    branches = "all" if ctx.scope.branch_ids is None else ", ".join(map(str, sorted(ctx.scope.branch_ids))) or "none"
    system = [
        {"type": "text", "text": persona(a.name), "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": f"Today: {date.today().isoformat()}. User role: {ctx.scope.role}. "
                                 f"Branch ids in scope: {branches}. Payroll visible: {ctx.scope.payroll}."},
    ]
    messages = _history(ctx.db, a.name, user_key) + [{"role": "user", "content": text}]
    by_name = {t.name: t for t in tools}
    extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"} if s.claude_fallbacks else {}
    for _ in range(MAX_STEPS):
        resp = client.beta.messages.create(
            model=s.claude_model, max_tokens=4000, system=system, messages=messages,
            tools=[t.schema() for t in tools], output_config={"effort": s.claude_effort}, **extra)
        if resp.stop_reason == "refusal":
            return "I can't help with that request."
        if resp.stop_reason != "tool_use":
            return "\n".join(b.text for b in resp.content if b.type == "text").strip() or "—"
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            t = by_name.get(b.name)
            if not t:  # tool above the user's role: model never had it, but be safe
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": "not allowed", "is_error": True})
                continue
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": execute(ctx, t, dict(b.input))})
        messages.append({"role": "user", "content": results})
    return "Too many steps — please narrow the question."


# ---------------- offline / command mode ----------------

def offline_answer(ctx: Ctx, a, tools, text: str) -> str:
    allowed = {t.name for t in tools}
    parts = text.strip().split()
    cmd = parts[0].split("@")[0].lower() if parts else ""
    if cmd in a.commands:
        name, args = a.commands[cmd]
        if name == "find_sop" and len(parts) > 1:
            args = {"query": " ".join(parts[1:])}
    else:
        name, args = (tools[0].name if tools else None), {}
        if a.name in ("ozoda", "suhayl") and any(k in text.lower() for k in ("sop", "qoida", "правил", "rule")):
            name, args = "find_sop", {"query": text}
    if not name or name not in allowed:
        return "This command is outside your rights."
    data = json.loads(execute(ctx, TOOLS[name], args))
    return render(name, data)


def render(name: str, data) -> str:
    if isinstance(data, dict) and "error" in data:
        return f"⚠️ {data['error']}"
    if name == "attendance_day":
        lines = [f"📊 {data['date']}: came {data['came']} of {data['scheduled']} · late {data['late']} · "
                 f"not marked {data['unmarked']} · review {data['needs_review'] + data['conflict']}"]
        for b, v in list(data["by_branch"].items())[:12]:
            lines.append(f"• {b}: {v.get('came', 0)}/{v['total'] - v.get('off', 0)}")
        return "\n".join(lines + ["not marked ≠ absent"])
    if name == "payroll_precheck":
        lines = [f"💰 {data['month']}: {data['count']} issue(s), at risk: {data['amount_at_risk'] if data['amount_at_risk'] is not None else '—'}"]
        lines += [f"• {i['full_name']}: {i['detail']}" for i in data["issues"][:10]]
        return "\n".join(lines)
    return json.dumps(data, ensure_ascii=False, indent=1, default=str)[:3500]
