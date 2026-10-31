"""Telegram HTML helpers (telegram-rich-format skill): premium emoji with a normal fallback, escaping, safe splitting."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from ..config import cfg

LIMIT = 4096


@lru_cache
def _emoji() -> dict:
    return json.loads((Path(__file__).resolve().parents[1] / "tg_emoji.json").read_text("utf-8"))


def e(name: str) -> str:
    """Premium emoji (renders when the bot owner has Telegram Premium), plain emoji otherwise."""
    it = _emoji().get(name) or {}
    fb = it.get("fallback", "•")
    if it.get("id") and cfg("bot.premium_emoji", True):
        return f'<tg-emoji emoji-id="{it["id"]}">{fb}</tg-emoji>'
    return fb


def me(name: str) -> str:
    """Premium emoji in rich Markdown: ![fallback](tg://emoji?id=ID); plain emoji when the registry has no id."""
    it = _emoji().get(name) or {}
    fb = it.get("fallback", "•")
    return f"![{fb}](tg://emoji?id={it['id']})" if it.get("id") and cfg("bot.premium_emoji", True) else fb


def md(s) -> str:
    """Escape user text for rich Markdown (names, departments) — table pipes and markup characters."""
    out = str(s)
    for ch in "\\|*_`~[]#<>=":
        out = out.replace(ch, "\\" + ch)
    return out.replace("\n", " ")


def md_table(head: list[str], rows: list[list], align: str = "") -> str:
    """Rich Markdown table; align: one char per column, l / c / r."""
    al = {"l": ":---", "c": ":-:", "r": "---:"}
    sep = [al.get((align or "")[i:i + 1], ":---") for i in range(len(head))]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join(sep) + "|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


_URL = re.compile(r"(?<![(<\[\"'=/\w])https?://[^\s<>()\[\]`\"']+")
_CODE = re.compile(r"(```.*?```|`[^`\n]*`)", re.S)
LONG_URL = 40


def short_links(text: str, word: str = "Link") -> str:
    """Bare long URLs in agent Markdown -> [Link](url): neater than a two-line hh link. Code and existing links untouched."""
    def one(m: re.Match) -> str:
        url = m.group(0)
        tail = ""
        while url and url[-1] in ".,;:!?":
            url, tail = url[:-1], url[-1] + tail
        return (f"[{word}]({url})" if len(url) > LONG_URL else url) + tail
    parts = _CODE.split(text or "")
    return "".join(p if i % 2 else _URL.sub(one, p) for i, p in enumerate(parts))


def esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def split(text: str, limit: int = LIMIT) -> list[str]:
    """Split at blank lines (block boundaries) so no tag is ever cut; a single huge block is cut by lines."""
    out, cur = [], ""
    for block in text.split("\n\n"):
        piece = block if not cur else "\n\n" + block
        if len(cur) + len(piece) <= limit:
            cur += piece
            continue
        if cur:
            out.append(cur)
        if len(block) <= limit:
            cur = block
            continue
        cur = ""
        for line in block.split("\n"):
            if len(cur) + len(line) + 1 > limit:
                out.append(cur)
                cur = ""
            cur += ("\n" if cur else "") + line
    if cur:
        out.append(cur)
    return out
