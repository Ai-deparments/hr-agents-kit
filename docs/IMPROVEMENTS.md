# Improvements over the original system, and the roadmap

## Done in this kit

| Problem in the original setup | Solution here |
|---|---|
| The brand was hard-coded in about 15 files (personas, ad template, banner, panel) | `config/company.yaml` plus persona templates with `{company}` |
| Two databases (agents and panel) with an hourly copy that lost hire date, branch, leave balance and manager | One database for everything; no sync |
| Branch heads saw network-wide summaries in the bots; there was only a department-level search filter | `Scope` with branch ids in every service and tool; regional manager = several branches |
| Suhayl could return a colleague's onboarding plan by name; only the prompt forbade it | `my_*` tools take no person argument; identity comes from the Telegram link |
| No approve/reject screen for requests; Suhayl's requests never reached the panel | One `LeaveRequest` table, decisions in the panel with a required reason; an approved vacation becomes an `Absence` in the tabel |
| Agents had no way to ask for human-only actions | Approvals queue (`request_human_action`), decided in the panel |
| Payroll agent ran on demo tables with a hard-coded period `2026-09` | Pre-check runs on live tabel + entries for any month |
| Onboarding progress was always 0% (no "item done") | Checklist items from position templates, done/undone, traffic light |
| One 09:00–18:00 schedule; overnight shifts unverified | Fixed, 2/2 and 24/48 schedules with a per-person anchor; a shift ends at the last check-out before the next check-in (≤ 30 h); norm from the person's own schedule |
| No sales % in the formula | `SalesRecord` CSV import + `payroll.sales_percent` |
| No document expiry module | `Document` + expiring list + reminders (configured lead time, 7 days, day of) |
| No automatic triggers | Scheduler: reports, per-branch reports to heads, documents, 30/60/90 milestones, payroll 2 days before payday, stale requests |
| Seven bot tokens to manage | Optional **hub bot** with a keyword/`@agent` router |
| Mini App search was "department → name"; linking had no check | "branch → name → last 4 phone digits"; one Telegram per person |
| Two SOP libraries | One `Sop` table, upload `.md` from the panel |
| Unprotected web dashboard for recruiting | All panel routes are behind JWT; the Mini App needs a Telegram signature; agent API needs a key |

## v0.2 (2026-10-17): added after the security audit and research

| Feature | Why |
|---|---|
| **Anti-fraud check-in** (`attendance.check_mode`: geo / qr / geo_or_qr) | GPS pins are easy to fake. "Keldim" now needs the branch geofence (Telegram LocationManager, accuracy checked), or a 6-digit QR code that rotates every 60 s on the head's phone (Mini App → QR tab, scanned with Telegram's native scanner). Each event stores how it was verified |
| **Labor Code rules** (`labor.*`) | Early vacation (under 6 months of service) is flagged for the approver. Payroll pre-check warns when overtime goes over 120 h a year |
| **SOP read receipts** | Employees confirm "read" in Suhayl for the current version of each SOP. Monday reminders go to those who have not. The panel shows the % read per SOP |
| **Anonymous eNPS and exit survey** | The monthly 0–10 question and the exit-reason buttons go out through the bot. Answers are stored with no person id, and any group smaller than 5 is hidden |
| **Turnover-risk signals** | Explainable rules: lateness or absence trending up, first 90 days, warnings, swap or sick requests. HR only, and a reason to talk — never a decision |
| **Candidate consent + retention purge** | The recruiter bot asks for consent before the interview. A nightly job anonymises rejected and stale candidates after 180 days |
| **AI disclosure** | Each bot's `/start` says it is an AI assistant and that people make the decisions (Uzbekistan AI law) |
| **Golden evals** (`backend/evals/golden.yaml`) | Routing, role refusals and banned interview questions, run in CI. They already caught 2 gaps in the question filter |
| **Rauf recruiter panel + HR Mini App** | `/rauf` and `/m/rauf` |

## v0.3.1 (2026-10-30)

Ported from the v0.2-based branch into the v0.3 architecture; the gap analysis is in [V03_GAP.md](V03_GAP.md).

| Feature | Why |
|---|---|
| **AI camera webhook** (`POST /api/webhooks/camera`, `services/camera.py`) | Camera services post arrivals / leaves / hourly visitor counts / a day timesheet. HMAC over `<X-Timestamp>.<body>`, ±5 min, body cap, `X-Delivery-Id` processed once. Exact name match only (unmatched / ambiguous kept, never guessed); earliest arrival / latest leave; any human or time-system mark wins; photo / base64 fields stripped before saving. Group report: one count line; unmatched names only privately |
| **Discipline rules** (`discipline.rules`, Panel → Discipline rules) | Rules (N warnings, then a fine; window month / all time / per case) come from config; admins edit texts and amounts with before/after audit; a person applies a rule, which writes a warning or penalty entry with a snapshot amount (blocked in a closed month). Read-only `discipline_rules` tool |
| **Vacancy studio** (`services/ad_check.py`, `services/vacancies.py`) | Company facts (admin) are the only extra facts; 2 agent variants with template fallback; pick in words (code first, the model may only label 1 / 2); every free text passes the checker; publish only on the exact confirm word (bot and agent tool); "task for the agent" queue with a human Apply; channel post without an inline button |
| **Invite / Reject with preview** (`services/hiring.py`, `services/outbox.py`) | Exact message preview, 409 if it changed; outbox rows claimed before sending (at most once) and deduped; free-text booking mapped only to offered slots; atomic conditional-UPDATE booking; move / cancel by text; reminders the day before at 18:00 and 1 h before |
| **Hire → onboarding handoff** (`OnboardingHandoff`) | "Hired" in the panel / Mini App now leads to a waiting list: one click = card + 30/60/90 plan + course; dismiss with a reason; waiting count in the onboarding topic report |
| **Tabel-close reminder, weekly signals** | From the 1st until last month's tabel is closed (HR heads, counts only). Per-branch lateness / confirmed absences / early leaves vs the previous 4 weeks (≥ 3 and ≥ 2×): group count only, details privately; HR agent tool + Analytics card |

### Upgrade from v0.3

1. Pull, then rebuild: `docker compose up -d --build` (or restart `uvicorn` and `python -m app.bots.main`).
2. Schema: on start `init_db()` creates the new tables (`camera_*`, `discipline_*`, `ad_variants`, `agent_jobs`,
   `onboarding_handoffs`) and adds the new columns (`vacancies.ad_custom`, `outbox.claimed_at` / `dedupe_key`,
   `interview_slots.reminded_day` / `reminded_hour` / `booked_at`). Nothing to run by hand; on Postgres the new
   `outbox.dedupe_key` column has no index on an upgraded database — add `CREATE INDEX ix_outbox_dedupe_key ON outbox (dedupe_key)` if the outbox is large.
3. Seed the discipline rules: `docker compose run --rm api python -m app.seed --no-demo` (idempotent; edits made in the panel are kept).
4. Config (`config/company.yaml`, copy from the example): `camera.*`, `discipline.rules`, `recruiting.publish_confirm_words`,
   `recruiting.interviews.*`, `payroll.tabel_close_reminder`, `reports.weekly_signals`.
5. Env: `CAMERA_WEBHOOK_SECRET` (random, ≥ 32 chars) only if an AI camera will post to the kit; without it the endpoint answers 503.
6. Behaviour changes: Reject in the panel now sends the candidate a polite message (preview first); a booked candidate who
   writes to the bot gets the booking repeated (or moves / cancels it) instead of silence; interview reminders moved from
   ~2 h before to the day before at 18:00 + 1 h before; already-booked slots from v0.3 get the 1 h reminder only.

## Next (roadmap)

Ranked by value for effort, from the 2026-10 research:

1. **Shift-swap marketplace.** An employee posts a shift, an eligible colleague (same role, no rest-time or 120 h conflict) claims it, the head approves with one tap, and the timesheet updates.
2. **SOP quiz.** After "read", 3–5 questions as native Telegram quiz polls; store the score next to the receipt.
3. **Interview no-shows.** (Scheduling and reminders are done in v0.3.1.) On a no-show the bot offers the slot to the next candidate.
4. **Webhook mode for bots.** Use `secret_token` checked through `X-Telegram-Bot-Api-Secret-Token`, instead of polling.
5. **RAG over SOPs.** pgvector, answers quote the SOP id and section, "I don't know" below the threshold, role filter at retrieval.
6. **LLM observability.** Self-hosted Langfuse or OpenTelemetry: cost and latency per agent, plus nightly golden runs against Claude.
7. **Automatic shift-schedule draft.** OR-Tools CP-SAT; the head approves the result.
8. **Document intake with a vision model.** Diploma and medical book fields filled by the model and checked by a human; the raw image is deleted after verification.


Also planned:

1. **Voice:** speech-to-text for Suhayl and Rauf, and Russian + Uzbek text-to-speech (needs keys and the client's consent to send audio to cloud services).
2. **Userbot for the ads agent:** a separate MTProto worker for searching channels and messaging admins. It keeps the existing safety rules: a human presses the first message; budget, red flags and the "never say paid" rule are checked in code.
3. **hh.uz / vacandi.uz / osonish.uz connectors** in `services/recruiting.py`.
4. **Sales from POS/ERP** in place of the CSV import.
5. **Geofence / branch Wi-Fi check** on "Keldim", if the client wants it.
6. **Night and holiday multipliers** in the payroll formula.
7. **Eval set:** 20–30 real questions per agent with expected numbers from a fixed seed, run in CI against the offline tools and nightly against Claude.
8. **Postgres + Alembic migrations** for multi-instance deployments.
