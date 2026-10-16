"""Runtime settings (env) + company profile (YAML)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _ids(name: str) -> set[int]:
    raw = os.getenv(name, "")
    return {int(x) for x in raw.replace(" ", "").split(",") if x}


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'hr.db'}"))
    company_file: Path = field(default_factory=lambda: Path(os.getenv("COMPANY_FILE", ROOT / "config" / "company.yaml")))
    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", "dev-only-change-me"))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "0") == "1")
    # Telegram
    owner_ids: set[int] = field(default_factory=lambda: _ids("OWNER_IDS"))
    hr_head_ids: set[int] = field(default_factory=lambda: _ids("HR_HEAD_IDS"))
    payroll_restricted_ids: set[int] = field(default_factory=lambda: _ids("PAYROLL_RESTRICTED_IDS"))
    report_chat_id: int | None = field(default_factory=lambda: int(os.getenv("REPORT_CHAT_ID")) if os.getenv("REPORT_CHAT_ID") else None)
    webapp_url: str = field(default_factory=lambda: os.getenv("WEBAPP_URL", "http://localhost:5173"))
    hub_bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN_HUB", ""))
    # Dev only: lets the Mini App run in a normal browser as this Telegram user
    dev_telegram_id: int | None = field(default_factory=lambda: int(os.getenv("DEV_TELEGRAM_ID")) if os.getenv("DEV_TELEGRAM_ID") else None)
    # LLM
    claude_model: str = field(default_factory=lambda: os.getenv("CLAUDE_MODEL", "claude-opus-5-5"))
    claude_effort: str = field(default_factory=lambda: os.getenv("CLAUDE_EFFORT", "low"))
    claude_fallbacks: bool = field(default_factory=lambda: os.getenv("CLAUDE_FALLBACKS", "1") == "1")
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))

    def bot_token(self, agent: str) -> str:
        return os.getenv(f"BOT_TOKEN_{agent.upper()}", "")


@lru_cache
def settings() -> Settings:
    return Settings()


@lru_cache
def company() -> dict:
    s = settings()
    path = s.company_file if s.company_file.exists() else ROOT / "config" / "company.example.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def cfg(path: str, default=None):
    """cfg('attendance.late_grace_min', 10)"""
    node = company()
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node
