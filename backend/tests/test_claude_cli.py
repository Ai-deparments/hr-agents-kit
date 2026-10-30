"""Claude Code CLI mode: tool loop + interview scoring, with the CLI faked."""
from app.agents import claude_cli, runtime
from app.rbac import scope_for_telegram
from app.services import interview


def test_cli_tool_loop_runs_allowed_tool_then_answers(db, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "claude_cli")
    monkeypatch.setenv("CLAUDE_CLI", "/bin/claude")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "x")
    seen = []

    def fake(system, prompt, schema=None, timeout=150):
        seen.append(prompt)
        if len(seen) == 1:
            return {"tool": "my_card", "args_json": "{}", "answer": ""}
        assert "TOOL my_card" in prompt  # tool result went back to the model
        return {"tool": "", "args_json": "{}", "answer": "Sizning jadvalingiz tayyor"}

    monkeypatch.setattr(claude_cli, "ask", fake)
    scope = scope_for_telegram(db, 2001)  # linked employee
    assert runtime.run_agent(db, "suhayl", scope, "jadvalim qanaqa?", "tg:2001") == "Sizning jadvalingiz tayyor"


def test_cli_tool_outside_role_is_refused(db, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "claude_cli")
    monkeypatch.setenv("CLAUDE_CLI", "/bin/claude")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "x")
    calls = []

    def fake(system, prompt, schema=None, timeout=150):
        calls.append(prompt)
        if len(calls) == 1:
            assert "payroll_precheck" not in system  # tool above the role is not even listed
            return {"tool": "payroll_precheck", "args_json": "{}", "answer": ""}
        assert "tool not allowed" in prompt
        return {"tool": "", "args_json": "{}", "answer": "ok"}

    monkeypatch.setattr(claude_cli, "ask", fake)
    assert runtime.run_agent(db, "suhayl", scope_for_telegram(db, 2001), "oylik?", "tg:2001-b") == "ok"


def test_cli_scoring_is_clamped(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "claude_cli")
    monkeypatch.setenv("CLAUDE_CLI", "/bin/claude")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "x")
    monkeypatch.setattr(claude_cli, "ask", lambda *a, **k: {c: {"score": 150, "comment": "ok"} for c in interview.CRITERIA})
    out = interview.score_answers(None, [{"q": "q", "a": "a"}])
    assert all(v["score"] == 100 for v in out.values())
