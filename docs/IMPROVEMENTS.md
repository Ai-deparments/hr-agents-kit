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

## Next (roadmap)

1. **Voice:** speech-to-text for Suhayl and Rauf, and Russian + Uzbek text-to-speech (needs keys and the client's consent to send audio to cloud services).
2. **Userbot for the ads agent:** a separate MTProto worker for searching channels and messaging admins. It keeps the existing safety rules: a human presses the first message; budget, red flags and the "never say paid" rule are checked in code.
3. **hh.uz / vacandi.uz / osonish.uz connectors** in `services/recruiting.py`.
4. **Sales from POS/ERP** in place of the CSV import.
5. **Geofence / branch Wi-Fi check** on "Keldim", if the client wants it.
6. **Night and holiday multipliers** in the payroll formula.
7. **Eval set:** 20–30 real questions per agent with expected numbers from a fixed seed, run in CI against the offline tools and nightly against Claude.
8. **Postgres + Alembic migrations** for multi-instance deployments.
