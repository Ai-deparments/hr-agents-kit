"""Claude through the Claude Code CLI on a subscription (no API key): `claude -p` in the background.
Auth: CLAUDE_CODE_OAUTH_TOKEN from `claude setup-token`. Built-in tools are disabled, sessions are not stored,
the CLI runs in an empty directory, one call at a time (the CLI is heavy for a small server)."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import threading

log = logging.getLogger("claude_cli")
_lock = threading.Lock()


class CliError(Exception):
    pass


def enabled() -> bool:
    return os.getenv("LLM_MODE") == "claude_cli" and bool(os.getenv("CLAUDE_CLI")) and bool(os.getenv("CLAUDE_CODE_OAUTH_TOKEN"))


def _env() -> dict:
    home = os.getenv("CLAUDE_HOME", os.path.join(tempfile.gettempdir(), "claude-home"))
    os.makedirs(home, exist_ok=True)
    keep = {k: os.environ[k] for k in ("PATH", "LANG", "CLAUDE_CODE_OAUTH_TOKEN") if k in os.environ}
    return {**keep, "HOME": home, "CLAUDE_CONFIG_DIR": os.path.join(home, ".claude"), "DISABLE_AUTOUPDATER": "1",
            "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}


def ask(system: str, prompt: str, schema: dict | None = None, timeout: int = 150):
    """Returns text, or a dict when `schema` is given (structured output)."""
    args = [os.environ["CLAUDE_CLI"], "-p", "--output-format", "json", "--system-prompt", system,
            "--tools", "", "--no-session-persistence", "--strict-mcp-config", "--setting-sources", "",
            "--model", os.getenv("CLAUDE_CLI_MODEL", "sonnet")]
    if schema:
        args += ["--json-schema", json.dumps(schema)]
    with _lock, tempfile.TemporaryDirectory() as cwd:
        try:
            p = subprocess.run(args, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=_env())
        except subprocess.TimeoutExpired as e:
            raise CliError("timeout") from e
    try:
        out = json.loads(p.stdout)
    except ValueError:
        log.error("claude cli failed rc=%s: %s", p.returncode, (p.stderr or p.stdout)[-300:])
        raise CliError("bad output")
    if out.get("is_error"):
        raise CliError(str(out.get("result") or out.get("subtype"))[:200])
    if not schema:
        return (out.get("result") or "").strip()
    data = out.get("structured_output")
    if data is None:
        try:
            data = json.loads(out.get("result") or "")
        except ValueError as e:
            raise CliError("no structured output") from e
    return data
