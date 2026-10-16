---
name: telegram-rich-format
description: Write beautiful Telegram messages, channel posts, reports and alerts with Bot API HTML formatting — bold/italic/underline/strike, spoilers, links, code blocks with syntax highlighting, block and expandable quotes, live date-time (tg-time) and PREMIUM (custom) emoji via :shortcodes:. Includes a validator/renderer (tgfmt.py) for tags, nesting, escaping and length limits. Use whenever a message, report, post, notification or digest is sent to Telegram (Bot API, Composio TELEGRAM_SEND_MESSAGE, Hermes/Atlas replies), or the user asks for "красивое оформление", "премиум эмодзи", "chiroyli xabar".
version: 1.0.0
license: MIT
---

# Telegram rich format

Always format with **HTML** (`parse_mode=HTML`). It is the most predictable mode:
only `<`, `>` and `&` need escaping. MarkdownV2 requires escaping 18 characters and
breaks on every unescaped `.` or `-`.

## Tag reference (Bot API HTML)

| Effect | HTML |
|---|---|
| Bold | `<b>text</b>` |
| Italic | `<i>text</i>` |
| Underline | `<u>text</u>` |
| Strikethrough | `<s>text</s>` |
| Spoiler (hidden) | `<tg-spoiler>text</tg-spoiler>` |
| Link | `<a href="https://…">text</a>` |
| User mention | `<a href="tg://user?id=123">name</a>` (only works in links/buttons) |
| Inline code | `<code>text</code>` |
| Code block | `<pre>text</pre>` |
| Code block + highlight | `<pre><code class="language-python">…</code></pre>` |
| Quote | `<blockquote>text</blockquote>` |
| Collapsible quote | `<blockquote expandable>long text</blockquote>` |
| Premium emoji | `<tg-emoji emoji-id="5368324170671202286">👍</tg-emoji>` |
| Live date/time | `<tg-time unix="1791306000" format="wDT">tue 20:00</tg-time>` — `r` relative ("in 2 hours"), `w` weekday, `d`/`D` short/long date, `t`/`T` short/long time |

Not available to bots: headings, tables, lists as entities, formulas (the app's "Article"
editor). Imitate them: a bold line as a heading, `1.`/`•` lines as lists, aligned columns
inside `<pre>` as a table, or publish long-form on telegra.ph and link it.

## Rules

1. Escape text: `&` → `&amp;`, `<` → `&lt;`, `>` → `&gt;` everywhere outside tags
   (user names, captions, code samples, error messages).
2. Nesting: b/i/u/s/spoiler can wrap anything except code/pre; blockquotes cannot nest;
   nothing goes inside `<code>`; only `<code class="language-…">` inside `<pre>`.
3. Limits: message **4096** characters, media caption **1024** (counted without tags).
   Split long reports at paragraph boundaries, never inside an open tag.
4. Links: real `https://` URLs only; turn link previews off for reports.
5. Style: one idea per line, blank line between blocks, bold for the headline and key
   numbers, emoji as bullets (not more than one per line), collapsible quote for details,
   spoiler only for a reveal/answer, no walls of bold.

## Premium (custom) emoji

Write shortcodes from `emoji.json`: `:fire:`, `:rocket:`, `:chart_up:`, `:robot:`, `:check:`…
`tgfmt.py render` turns them into `<tg-emoji>` with a normal emoji fallback inside.

- They render only when the **bot owner has Telegram Premium** (private chats, groups,
  supergroups) or the bot has a **Fragment-purchased username**. In channels without a
  Fragment username, and for non-premium readers of forwards, the fallback emoji shows.
  So posts always look fine — premium is an upgrade, never a dependency.
- For channel posts without a Fragment username use `--no-premium`.
- Ids: forward the emoji to @idstickerbot (or similar), or list a whole pack with
  `tgfmt.py pack <sticker_set_name>`; put ids into `emoji.json`. Never invent ids.

## Workflow

```bash
S=~/.claude/skills/telegram-rich-format/scripts/tgfmt.py
python $S list                         # available :shortcodes:
python $S render draft.html            # → final HTML on stdout, problems on stderr
python $S check  final.html --caption  # validate a caption (1024 limit)
TELEGRAM_BOT_TOKEN=… python $S send draft.html --chat 123456   # manual test send
```
Exit code 1 = problems found; fix them before sending.

Templates in `templates/`: `report.html` (daily metrics), `post.html` (channel post),
`alert.html` (decision request with `<tg-time>`).

## Sending

- **Bot API / Composio** (`TELEGRAM_SEND_MESSAGE`): pass the rendered HTML as `text`
  with `parse_mode: "HTML"`; photo captions ≤1024.
- **Agent gateways that convert replies to MarkdownV2 by default** (e.g. a personal
  multi-agent assistant with cron deliveries): start the reply with the marker
  `<!--tg-html-->` and write Telegram HTML after it — the gateway then sends it as HTML
  as-is (premium emoji, quotes, spoilers, tg-time), escapes any text before the marker,
  splits long messages safely and falls back to plain text if Telegram rejects the markup.
  Write `<tg-emoji emoji-id="…">🔥</tg-emoji>` directly (shortcodes are not expanded there);
  take ids from `emoji.json`.
