---
name: default-stack
description: >
  The fixed default tech stack and conventions for every new project, feature, AI agent, Telegram bot, Mini App,
  dashboard or admin panel. Use BEFORE writing code or a plan whenever a technology choice would otherwise be
  asked ("which framework?", "Python or Node?", "which DB / UI lib / bot library / model?"), when scaffolding a repo,
  adding a dashboard, chart, report, bot or agent, or when the user says "yangi loyiha", "новый проект",
  "dashboard qil", "сделай дашборд", "bot yoz", "агент сделай". Do NOT ask the user which stack to use —
  apply this one and only mention deviations.
---

# Default stack — decide, don't ask

Apply these choices without asking. Ask only when the user's request contradicts them
or the existing repo already uses something else (then follow the repo).

## Backend & agents

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| API | FastAPI + Pydantic v2, routers in `app/api/*.py` |
| DB | SQLAlchemy 2.0 (typed `Mapped[...]`), SQLite for dev/pilot, Postgres for production |
| Auth (panel) | JWT (PyJWT, HS256, secret ≥ 32 chars from env), argon2 password hashes, 8 tries / 10 min limit |
| Auth (Telegram Mini App) | Verify `initData` HMAC (`WebAppData` key), max age 1 h, then issue own JWT |
| Bots | aiogram 3, HTML parse mode; one process; per-agent tokens or one hub bot with a router |
| Scheduling | APScheduler (`AsyncIOScheduler`, company timezone) |
| Excel | openpyxl |
| LLM | Official `anthropic` SDK, Messages API, manual tool-use loop; default model `claude-opus-5-5`, effort `low` for chat agents; cache the persona with `cache_control`; server-side fallbacks on. Model and effort come from env |
| No API key | Agents still work in **offline mode**: slash commands call the same tools deterministically |
| Tests | pytest + FastAPI `TestClient`; temp SQLite; seed demo data in a session fixture |
| Config | Business rules in one `config/company.yaml`; secrets only in `.env` (never committed, `.env.example` documented) |

## Frontend, dashboards, Mini Apps

| Layer | Choice |
|---|---|
| App | React 18 + Vite + TypeScript, no UI kit; plain CSS with design tokens on `:root`, light + dark |
| Routing | `/` panel, `/m` Telegram Mini App (same bundle) |
| Data | `fetch` wrapper with bearer token; Vite proxy `/api` → `:8000`; backend serves `web/dist` in prod |
| Charts | Inline SVG or a small chart helper; follow a dataviz palette; numbers with base & period |
| i18n | `uz` (default), `ru`, `en` dict in `src/i18n.ts`; switcher in the header |
| Layout | Works at 375 px; tables scroll inside their card, never the page |
| Look | Calm, professional, brand color from config; no emoji in UI chrome |

Telegram messages and reports: use the `telegram-rich-format` skill (HTML, premium emoji, validator).
UI screenshots / redesigns: `screens-overview`, `redesign-mockup`. Lag: `perf-lag-audit`.

## Deploy

Docker multi-stage (node build → python slim, non-root user), `docker compose` with `api` + `bots` services,
volume for data, API bound to `127.0.0.1`, TLS reverse proxy (Caddy) in front. CI: GitHub Actions — `pytest -q` + `npm run build`.

## Conventions every project follows

- **Repo layout:** `config/`, `backend/app/{models,rbac,auth,config,seed}.py`, `backend/app/{services,agents,api,bots}/`, `backend/tests/`, `web/src/{panel,miniapp}/`, `docs/`.
- **Scope in code:** every service function takes a `Scope` (role, branch ids, payroll flag). Never filter access only in a prompt.
- **Tools are role-gated.** A tool above the user's role is not sent to the model at all.
- **Human-only decisions:** payroll approval, deductions, contract changes, hire, fire, mass broadcast and request approval. Agents only call `request_human_action`.
- **Data honesty:** unknown = `—` (never 0); "not marked" ≠ "absent"; every number shows its base and period.
- **Audit:** every agent message, tool call, money entry and decision goes to `audit_log`.
- **Money:** integers in the smallest currency unit; reasons are mandatory; entries are cancelled, never deleted.
- **Language:** code, identifiers and commits in English. User-facing text in uz / ru (and en when needed). READMEs in Uzbek + Russian.
- **Before shipping:** run the `security-audit` skill. For a deep audit, also run `cloudflare-security-audit`.
- **Commits:** small and focused, ending with the agreed co-author line. Never commit `.env`, keys, `*.session` or databases.

## When the repo differs

If the project already has another stack (for example Node/grammY, Next.js or Prisma), keep it. Apply only the
"Conventions" section, and say in one line that you are following the existing stack.
