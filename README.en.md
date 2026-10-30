# HR Agents Kit

A white-label HR department you can deploy for any business with shifts and many branches (pharmacies, retail, clinics, restaurants):
**7 AI agents in Telegram + a web HR panel + a team-lead cabinet and check-in Mini App**, on one database and one config file.

It started from the NOVA-KIT HR system running at a water-production plant (BioLife). It was then adapted to a pharmacy chain (Ozone).
This kit is the generalised **default version**: the brand, branches, shifts and pay rules all live in `config/company.yaml`, so the code has no client names in it.

> Private repository. Author: Komron (CEO AI team, HR AI agents).

## What's inside

| Agent | Who uses it | Job |
|---|---|---|
| **Hamza** — HR lead & attendance | owner, HR head, branch heads | single HR entry point; 09:00 / 18:30 attendance reports + Excel; month tabel; asks up to 3 agents |
| **Ozoda** — onboarding | HR, heads | 30/60/90 plan from position templates, checklist, mentor, test scores, SOP lookup |
| **Bexruz** — payroll pre-check | owner, HR head, payroll | issues before payout + amount at risk; never calculates/approves |
| **Husayn** — analytics | owner, HR, heads | headcount, turnover (incl. "left in first 30 days"), attendance — always with base & period |
| **Suhayl** — employee helpdesk | every employee | my shift, leave balance, my requests, my plan, my documents, rules; creates requests |
| **Rauf** — recruiter | candidates / HR | live interview in Telegram, 4-criteria scoring, shortlist ≥ 70, vacancy drafts, SLA |
| **Reklama** — channel ads | HR owners | registers job channels with a budget; the first message and every payment are made by a person |

The **web panel** has these sections: dashboard, employees, attendance, tabel (time sheet: grid, manual edit with a required reason, Excel export, month close), payroll (formula with an explanation for every number, pre-check, approval flow), requests, approvals queue, onboarding, document expiry, recruiting, analytics, agent chat, SOP library, chat log, audit.
The **Mini App** has two parts. Employees tap "Keldim / Ketdim" (check in / check out), and link their Telegram as "branch → name → last 4 phone digits". Team leads get a cabinet: daily "came / absent" with hours from 0.5 to 24, the team's month, and advance / penalty / bonus / warning entries, each with a required reason.

**Rauf has his own recruiter panel at `/rauf`** (role recruiter, same login). It contains:
- a dashboard with open vacancies, candidates, average score, days to close and SLA lights;
- the funnel by stage and by source;
- a kanban pipeline;
- vacancies and candidates;
- the CV archive;
- channel-ad deals;
- integration status, without key values.

Everything is limited by branch scope.

**Rauf's HR Mini App** at `/m/rauf` opens from Rauf's bot, for HR Telegram IDs only. It shows candidates with their scores and the Shortlist / Hired / Reject buttons; a person makes every decision.

**New in v0.2:**
- **Anti-fraud check-in:** the branch geofence, or a QR code on the head's phone that rotates every 60 s.
- **Labor Code rules:** leave taken before 6 months of service is flagged, and overtime is capped at 120 h a year.
- **SOP read receipts**, with read coverage shown in the panel.
- **Anonymous eNPS and exit survey**, shown only for groups of 5+ answers.
- **Turnover-risk signals**, visible to HR only.
- **Candidate consent and a retention purge** for candidates' personal data.
- **Security audit:** see [docs/SECURITY.md](docs/SECURITY.md).

### New in v0.3

- **One HR agent** for managers, HR and the owner (all tools); employees get their own helper. No buttons — plain words only.
- **Context-aware agent:** reads the replied-to message, keeps vacancy drafts across /start, picks the language from the message text.
- **Vacancies** written from HR's words, edited and published only on command; public /jobs page.
- **Interview slots and job offers** answered in words; an accepted offer creates the employee card (probation) and the onboarding course.
- **HR documents as PDF** from editable templates (employment certificate, hire and leave orders); unknown fields stay blank.
- **Onboarding materials:** videos and guides by position/department, day-by-day course, "seen" receipts, talk reminders.
- **Reports per forum topic:** the bot learns topic names and posts each report (attendance, recruiting, onboarding, payroll, analytics) to its topic, morning and evening, and stays silent when there is nothing to say.
- **Phone-first formatting:** rich messages with headings and short lists instead of wide tables.
- **Weekly CEO digest** (rich + 3-sheet Excel) and **discipline reminders** drafted on Monday, sent only after HR approval.
- **Integrations:** TimePay (Face ID attendance, fines/bonuses), Smartup (sales), hh.uz (read-only résumé search), KPI and ABC analysis.
- **Panel:** users, bot access requests (strangers are ignored by the bot), role builder, departments.
- **More accurate attendance:** checked in without check-out counts as present; people with no marks for 30 days are listed separately and excluded from the rate.

### New in v0.3.1

- **AI camera → attendance.** A signed webhook (`POST /api/webhooks/camera`, HMAC, 5-minute window, a retried delivery counts once). The earliest arrival and the latest leave of the day are kept; a human mark (check-in, team lead, HR edit) always wins; photos are never stored; a name is linked only when it matches exactly one employee, the rest are kept for HR. A camera line in the attendance report (counts only in the group) and a read-only "AI camera" page.
- **Discipline rules.** The list lives in `company.yaml`; only an admin edits texts and amounts in the panel (audited before/after). A person applies a rule: N warnings first, then a fine; a recorded fine keeps its amount even if the rule changes later.
- **Vacancy studio.** A company facts block (approved by an admin) — the agent writes only from it and the vacancy card. The agent writes 2 variants; HR picks in words ("2", "the second one") or says what to change. Every text is checked: phones/links cut, numbers only from the sources, age only "18+", no gender/appearance/nationality/religion requirements. A "task for the agent" queue in the panel; a person applies the result. Publishing needs the exact confirm word ("e'lon qil" / "publish"); "don't publish" never publishes.
- **Invite / Reject with a preview.** HR sees the exact message the candidate gets; it is sent once (outbox). The candidate writes a time freely ("10:30", "12.11 10:30", in words) — the model may only map it to an offered slot; booking is atomic; moving / cancelling works in words too. Reminders the day before at 18:00 and 1 h before.
- **Hired → onboarding.** A candidate marked hired in the panel appears in Onboarding as waiting: one click creates the card + 30/60/90 plan + course; dismiss needs a reason. The onboarding report shows the waiting count.
- **Reports.** Payroll: from the 1st, daily until last month's timesheet is closed (no money in the text). Analytics: weekly per-branch signals (last 7 days ≥ 3 and ≥ 2× the average of the previous 4 weeks) — the group gets a count, branch details go privately.

Upgrade from v0.3: see [docs/IMPROVEMENTS.md](docs/IMPROVEMENTS.md#v031-2026-10-30).

## Built-in principles

- **Seven decisions are made by a person only:** payroll approval, deductions, contract change, hiring, firing, mass broadcast, request approval.
  An agent can only call `request_human_action`, which puts the request into the approvals queue.
- **Branch scope is enforced in code.** Every service takes a `Scope`: a pharmacy head sees only their pharmacy, a regional manager only their pharmacies.
  Tools above the user's role are never shown to the model.
- **The data never pretends:**
  - "not marked" is not shown as "absent";
  - a missing check-out goes to "needs review" (8 hours are never assumed);
  - an unknown salary is shown as `—`, not 0.
- **Source priority for a day:** HR edit > HR leave/sick > team-lead report > self check-in. When the lead says "absent" but a check-in exists, the day becomes a `conflict` for HR to review.
- **Audit log:** every message, tool call, report, rapport change, money entry and decision.

## Quick start (demo)

```powershell
cd backend
python -m venv .venv; .venv\Scripts\pip install -r requirements.txt
$env:DEBUG="1"; $env:DEV_TELEGRAM_ID="1001"     # 1001 = demo pharmacy head
.venv\Scripts\python -m app.seed                 # demo data from config/company.example.yaml
.venv\Scripts\python -m uvicorn app.main:app --reload
# second terminal
cd web; npm install; npm run dev                 # http://localhost:5173  (Mini App: /m)
```

Demo logins:
- `admin / admin12345`
- password `demo12345` for: `hr`, `buh` (payroll), `ceo`, `regional` (2 pharmacies only), `recruiter`

Without `ANTHROPIC_API_KEY` the agents run in **offline mode**: slash commands (`/hisobot`, `/payrollcheck`, `/tahlil`, `/onboarding`, `/menu` …) still return real data.

Bots: set `BOT_TOKEN_HUB` (one bot that routes to all agents) or `BOT_TOKEN_<AGENT>`, then run `python -m app.bots.main`.

## Deploy for a new client

1. `cp config/company.example.yaml config/company.yaml` and fill in:
   - brand;
   - regions and branches;
   - positions;
   - schedules (fixed, 2/2, 24/48);
   - pay rules (KPI cap, late penalty, % of sales, payday);
   - onboarding templates, document types, request kinds, SLA by position.
2. `cp .env.example .env`. Set `JWT_SECRET`, `ADMIN_PASSWORD`, bot tokens, Telegram IDs, `WEBAPP_URL` (HTTPS) and `ANTHROPIC_API_KEY`; `CAMERA_WEBHOOK_SECRET` only if an AI camera posts to the kit.
3. `docker compose up -d --build`, then `docker compose run --rm api python -m app.seed --no-demo`.
4. Load staff in the panel, then link people: branch heads in "Branch leads", employees through the Mini App.
5. Pilot on 2–3 branches (one of them 24/7) for 2 weeks, with payroll calculated in parallel for one month.

See [docs/IMPROVEMENTS.md](docs/IMPROVEMENTS.md) for the improvements over the original system and the roadmap.

## Tests

```powershell
cd backend; .venv\Scripts\python -m pytest -q
```

The tests cover:
- overnight 24-hour shifts;
- missing check-out going to review;
- unmarked ≠ absent, and source priority / conflicts;
- personal-schedule lateness;
- branch scope, Telegram roles, and tools hidden above the user's role;
- self-only onboarding plan;
- leave balance, and approval landing in the tabel;
- payroll formula and amount hiding;
- the human-only payroll flow;
- interview scoring and banned questions;
- the small-group % rule;
- offline agents and routing;
- API permissions;
- Mini App check-in;
- AI camera webhook (signature, replay window, dedupe, human marks win, no photos);
- discipline rules (admin-only edits, warnings → fine, snapshot amounts);
- ad checker, 2 variants, picking in words, confirm-word publish, agent tasks;
- invite / reject preview, outbox at most once, free-text and atomic booking, reminders;
- hire → onboarding handoff; tabel-close reminder; weekly per-branch signals.

## Layout

```
config/company.example.yaml   the only place a client is configured
backend/app/
  models.py  rbac.py  auth.py  config.py  seed.py
  services/  attendance · schedules · payroll · people · onboarding · analytics · recruiting · interview · reports · notifications
             camera · discipline · vacancies · ad_check · hiring · outbox · topic_reports · llm
  agents/    registry.py (agents) · tools.py (role-gated tools) · runtime.py (Claude tool loop + offline mode) · personas/*.md
  api/       panel.py · miniapp.py · agents.py
  bots/      main.py (aiogram: per-agent or hub bot, scheduler)
web/          React + Vite panel and Mini App
```
