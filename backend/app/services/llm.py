"""One structured-output call to Claude (API key or the Claude Code CLI). None when no model is configured (offline)."""
from __future__ import annotations

import json
import os


def ask_json(system: str, prompt: str, schema: dict, max_tokens: int = 2000) -> dict | None:
    if os.getenv("LLM_MODE") == "claude_cli":
        from ..agents import claude_cli
        return claude_cli.ask(system, prompt, schema, timeout=120) if claude_cli.enabled() else None
    from ..agents.runtime import llm_enabled
    if not llm_enabled():
        return None
    import anthropic
    from ..config import settings
    r = anthropic.Anthropic().messages.create(
        model=settings().claude_model, max_tokens=max_tokens, system=system,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}])
    return json.loads(next(b.text for b in r.content if b.type == "text"))
