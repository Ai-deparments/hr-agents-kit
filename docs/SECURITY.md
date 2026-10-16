# Security & compliance

## Audit — 2026-10-17 (v0.2)

**Scope.** The whole repository and its full git history. Method: a manual review against OWASP (web, API, LLM Top 10 2025), plus `pip-audit` and `npm audit`. Strix, the automated pentest tool, was not run because Docker is not installed.

### Leaks

**What was checked:**
- tokens: Anthropic, GitHub, Telegram bot, AWS, Google;
- JWTs and private keys;
- database URLs with passwords;
- IP addresses;
- personal e-mails and phone numbers.

**Result: nothing found.** `.env`, databases, `*.session` files and `config/company.yaml` are in `.gitignore`. All commits are signed with the GitHub no-reply address. The demo data uses fake names and random numbers.

### Findings (all fixed in this release, regression tests in `tests/test_security.py`)

| # | Severity | Finding | Fix |
|---|---|---|---|
| 1 | **High** | Mini App linking: any Telegram user could brute-force the last 4 phone digits (10 000 combinations, no limit). The full list of unlinked employees was also visible | 5 failures per Telegram account and 5 per employee card in 24 h (the card is then locked until HR links it). The list shows only "First L." and needs a Mini App session |
| 2 | **High** | Dependencies: `aiohttp 3.10.11` (66 CVEs) came in through `aiogram 3.15`; `vite`/`esbuild` (dev-server CVEs) | `aiogram 3.31`, `aiohttp ≥ 3.14.3`, `vite 8`. `pip-audit` and `npm audit` now report 0 |
| 3 | Medium | IDOR: a recruiter limited to certain branches could change candidates and open vacancies of other branches | Branch-scope check on candidate status, vacancy open and vacancy create |
| 4 | Medium | Personal data leaked into group chats: in a group, Suhayl or Bexruz answered with personal cards | In groups only aggregate commands (`/hisobot`, `/davomat`) are answered; everything else is sent to private chat |
| 5 | Medium | Excel formula injection: a name like `=HYPERLINK(...)` would run as a formula in the timesheet or attendance export | Text that starts with `= + - @` is written as plain text |
| 6 | Medium | Telegram HTML injection: employee names in reports and notifications were not escaped | Everything is escaped before `parse_mode=HTML` |
| 7 | Medium | A read-only `manager` could mark onboarding items and test scores; PATCH `status=fired` skipped the required reason | Writes need the `onboarding` permission; dismissal only through `/fire` with a reason |
| 8 | Medium | LLM10 (unbounded consumption): no per-user cap on model calls or interviews | 200 messages per user per day, 3 interviews per candidate per day (`limits.*`) |
| 9 | Low | Agent API key compared with `!=` | `hmac.compare_digest` |
| 10 | Low | `/docs` and OpenAPI exposed in production; no security headers; no body size limit; login limited only per username | Docs only with `DEBUG=1`. Added `nosniff`, `Referrer-Policy`, CSP `frame-ancestors` (Telegram only) and HSTS. 5 MB body limit, 2 MB upload limit. Login limited per IP as well |
| 11 | Low | Long sessions: panel 30 days, Mini App 7 days | Panel 7 days, Mini App 1 day (it re-authenticates with fresh `initData` on every open) |
| 12 | Low | Pharmacy heads always saw their team's salaries | `cabinet.heads_see_salary` (default `false`) |
| 13 | Low | Interview filter missed "Сколько вам лет?" and "Are you married?". The golden set caught it | Regex patterns. LLM-generated questions with protected topics fall back to the base set |

### Already in place (kept)

- Telegram `initData` checked with HMAC (`WebAppData` key), constant-time comparison, maximum age 1 h.
- Every service takes a `Scope`, so branch restrictions are enforced in code. Tools above the user's role are never sent to the model.
- The 7 human-only decisions cannot be made by an agent (`agent:*` actors are refused).
- Passwords are hashed with argon2. `JWT_SECRET` must be at least 32 characters, or the app does not start in production.
- The admin password must be set (`ADMIN_PASSWORD`) unless `DEBUG=1`.
- Docker runs as a non-root user, and the API is bound to `127.0.0.1` behind a TLS proxy.
- Audit log of every agent message, tool call, money entry and decision.

## Before production (checklist for the person deploying)

- [ ] Fill `.env` with a random `JWT_SECRET` and `ADMIN_PASSWORD`, `DEBUG=0`. Never commit `.env`.
- [ ] HTTPS domain with a reverse proxy (Caddy/nginx). Set `WEBAPP_URL` to that domain.
- [ ] In BotFather, keep the Bot API 10.2 Mini App origin restriction on (it is on by default).
- [ ] Choose `attendance.check_mode` and set branch geofences in Panel → Engagement → Check-in zones.
- [ ] Back up the database daily (volume `hrdata`) and test a restore.
- [ ] Run `pip-audit -r backend/requirements.txt` and `npm audit` before every release.
- [ ] Run the `security-audit` skill, and `cloudflare-security-audit` for a full audit.

## Uzbekistan legal notes (confirm with the client's lawyer)

Research summary from 2026-10. Each item still has to be confirmed against the text on lex.uz.

- **Personal data (ZRU-547, amended by Law No. 1125, 26 Mar 2026):**
  - Biometric and genetic data must be stored on servers in Uzbekistan.
  - Other personal data may be processed abroad: in one of the 49 adequate countries (list of 29 Jul 2026), or under approved contractual clauses.
  - A leak during a cross-border transfer must be reported within 24 h, with a follow-up within 72 h.
  - The kit stores **no biometrics**: GPS and the rotating QR code are used instead of face check-in. Keep it that way, or host on a server in Uzbekistan.
- **Database registration:** personal-data databases are registered with the Personalization Agency (pd.gov.uz), and a responsible person must be appointed. Candidate (recruiting) data probably needs registration.
- **Candidates:**
  - The recruiter bot asks for consent before the interview (`Candidate.consent_at`).
  - Rejected and stale candidates are anonymised after `recruiting.retention_days` (default 180) by the nightly job.
- **AI law (No. 1115, 21 Jan 2026) and the AI ethics order (No. 3787):**
  - A legally significant decision must not rest on AI output alone.
  - The 7 human-only gates and the audit log implement this.
  - The bots tell users they are AI assistants.
- **Labor Code (ZRU-798):**
  - Annual leave is at least 21 days and is due after 6 months of work.
  - Overtime is capped at 120 h per year.
  - Night work is 22:00–06:00.
  - These rules are in `labor.*`. Pay rates (overtime, night) are left as configuration until confirmed.
- **Employment contracts** are signed electronically on my.mehnat.uz. The kit does not replace this — HR hands off to it.
