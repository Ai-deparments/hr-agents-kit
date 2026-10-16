#!/usr/bin/env python3
"""tgfmt — render, check and send rich Telegram messages (Bot API HTML).

Commands
  render  FILE|-            :shortcode: → premium emoji, validate, print HTML
  check   FILE|-            validate already-rendered Telegram HTML
  send    FILE|- --chat ID  render + send via Bot API (token from $TELEGRAM_BOT_TOKEN)
  pack    SET_NAME          list custom emoji ids of a sticker set (fill emoji.json)
  list                      show emoji.json shortcodes

Options
  --caption          use the 1024-char caption limit instead of 4096
  --no-premium       render :shortcodes: as plain fallback emoji (e.g. for channels)
  --emoji PATH       custom emoji registry (default: ../emoji.json next to this script)

Only Python stdlib. Exit code 1 when validation finds problems.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

TEXT_LIMIT, CAPTION_LIMIT = 4096, 1024
ALLOWED = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "tg-spoiler", "span",
    "a", "code", "pre", "blockquote", "tg-emoji", "tg-time",
}
NO_NEST = {"blockquote"}          # blockquotes cannot be nested
LEAF = {"code", "pre"}            # only <code class="language-x"> may sit inside <pre>
TAG_RE = re.compile(r"<(/?)([a-zA-Z][\w-]*)((?:\s+[^<>]*?)?)\s*(/?)>")
SHORTCODE_RE = re.compile(r":([a-z0-9_+-]+):")
DEFAULT_EMOJI = Path(__file__).resolve().parent.parent / "emoji.json"


def load_emoji(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)}


def render(text: str, emoji: dict, premium: bool = True) -> str:
    """Replace :name: with <tg-emoji> (premium) or its fallback emoji."""

    def sub(m: re.Match) -> str:
        item = emoji.get(m.group(1))
        if not item:
            return m.group(0)
        fallback = item.get("fallback") or "⭐"
        if premium and item.get("id"):
            return f'<tg-emoji emoji-id="{item["id"]}">{fallback}</tg-emoji>'
        return fallback

    return SHORTCODE_RE.sub(sub, text)


def visible_length(text: str) -> int:
    """Length Telegram counts: text without tags, entities decoded (UTF-16 units)."""
    plain = html.unescape(TAG_RE.sub("", text))
    return len(plain.encode("utf-16-le")) // 2


def check(text: str, caption: bool = False) -> list[str]:
    problems: list[str] = []
    stack: list[str] = []
    for m in TAG_RE.finditer(text):
        closing, name, attrs = m.group(1) == "/", m.group(2).lower(), m.group(3) or ""
        if name not in ALLOWED:
            problems.append(f"unsupported tag <{name}> (escape it as &lt;{name}&gt; if it is text)")
            continue
        if name == "span" and not closing and 'class="tg-spoiler"' not in attrs:
            problems.append('<span> is only allowed as <span class="tg-spoiler">')
        if name == "tg-emoji" and not closing and not re.search(r'emoji-id="\d+"', attrs):
            problems.append("<tg-emoji> needs a numeric emoji-id")
        if name == "a" and not closing and not re.search(r'href="[^"]+"', attrs):
            problems.append("<a> needs href")
        if name == "tg-time" and not closing and not re.search(r'unix="\d+"', attrs):
            problems.append("<tg-time> needs unix=\"<seconds>\"")
        if closing:
            if not stack or stack[-1] != name:
                problems.append(f"unexpected </{name}> (open: {stack[-1] if stack else 'none'})")
            else:
                stack.pop()
        else:
            if name in NO_NEST and name in stack:
                problems.append("blockquotes cannot be nested")
            if stack and stack[-1] in LEAF and not (stack[-1] == "pre" and name == "code"):
                problems.append(f"<{name}> inside <{stack[-1]}> is not rendered")
            stack.append(name)
    if stack:
        problems.append(f"unclosed tags: {', '.join(stack)}")
    stray = re.sub(r"&(lt|gt|amp|quot|#\d+|#x[0-9a-fA-F]+);", "", TAG_RE.sub("", text))
    if "<" in stray or ">" in stray:
        problems.append("raw < or > in text: write &lt; / &gt;")
    if re.search(r"&(?!(lt|gt|amp|quot|#\d+|#x[0-9a-fA-F]+);)", TAG_RE.sub("", text)):
        problems.append("raw & in text: write &amp;")
    limit = CAPTION_LIMIT if caption else TEXT_LIMIT
    length = visible_length(text)
    if length > limit:
        problems.append(f"{length} characters > {limit} limit ({'caption' if caption else 'message'}): split it")
    if SHORTCODE_RE.search(TAG_RE.sub("", text)):
        problems.append("unknown :shortcode: left in text (see `tgfmt.py list`)")
    return problems


def _read(src: str) -> str:
    return sys.stdin.read() if src == "-" else Path(src).read_text(encoding="utf-8")


def _api(method: str, params: dict) -> dict:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("set TELEGRAM_BOT_TOKEN in the environment (never paste it into files)")
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        return json.loads(err.read().decode() or "{}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("render", "check", "send", "pack", "list"))
    ap.add_argument("source", nargs="?", default="-")
    ap.add_argument("--chat")
    ap.add_argument("--caption", action="store_true")
    ap.add_argument("--no-premium", action="store_true")
    ap.add_argument("--emoji", type=Path, default=DEFAULT_EMOJI)
    args = ap.parse_args()
    emoji = load_emoji(args.emoji)

    if args.command == "list":
        for name, item in emoji.items():
            state = item.get("id") or "no id yet → fallback"
            print(f":{name}:  {item.get('fallback', '')}  {state}  — {item.get('use', '')}")
        return 0
    if args.command == "pack":
        res = _api("getStickerSet", {"name": args.source})
        if not res.get("ok"):
            print(json.dumps(res, ensure_ascii=False))
            return 1
        for st in res["result"]["stickers"]:
            if st.get("custom_emoji_id"):
                print(f'{st.get("emoji", "")}\t{st["custom_emoji_id"]}')
        return 0

    text = _read(args.source)
    if args.command != "check":
        text = render(text, emoji, premium=not args.no_premium)
    problems = check(text, caption=args.caption)
    if args.command in ("render", "check"):
        print(text)
        for p in problems:
            print(f"✗ {p}", file=sys.stderr)
        return 1 if problems else 0
    if problems:
        for p in problems:
            print(f"✗ {p}", file=sys.stderr)
        return 1
    if not args.chat:
        sys.exit("--chat is required for send")
    res = _api("sendMessage", {"chat_id": args.chat, "text": text, "parse_mode": "HTML",
                               "link_preview_options": json.dumps({"is_disabled": True})})
    print(json.dumps({k: res.get(k) for k in ("ok", "description")}, ensure_ascii=False))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
