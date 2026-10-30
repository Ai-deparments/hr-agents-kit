# v0.3 → v0.3.1 gap analysis

Baseline: `main` @ 2389455 (v0.3). Reference implementation: the old `feat/agent-web-ports` branch (built on v0.2),
used only as a reference — every item below is re-implemented in the v0.3 architecture (one HR agent, outbox, topics).

| # | Feature | Upstream v0.3 already has? (file refs) | Action |
|---|---|---|---|
| 1 | AI-camera HMAC webhook → attendance (delivery dedupe, earliest arrival / latest leave, human marks win, photos never stored, camera line in the attendance report, read-only Camera page) | No. Attendance comes from the Mini App, team leads, HR edits and the TimePay importer (`importers/timepay.py`, pull, not a webhook). No camera source in `services/attendance.py`, no webhook route in `main.py` | **add** |
| 2 | Admin-editable discipline / fine rules (N warnings → fine, audit before/after, snapshot amounts) | No. Only weekly lateness *reminders* (`services/nudges.py`, `api/nudges.py`, `Nudges.tsx`) and manual `PayrollEntry` warning/penalty rows (`api/panel.py`). No rule table | **add** |
| 3a | Vacancy writer from HR's words, edit / rewrite with a comment, versions, publish on command, public `/jobs` + apply deep link | Yes: `services/vacancies.py` (`from_brief`, `rewrite`, `publish`, revisions), `api/vacancies.py` (`/api/public/jobs`), `web/src/Jobs.tsx`, `recruiting.apply_url`, bot `/start vac_N` | skip |
| 3b | Company facts block (the only facts the agent may use) | No (`company.description` in YAML only) | **add** |
| 3c | Agent writes 2 ad variants; HR picks or rewrites in natural language | No: one template text (`recruiting.render_ad`) | **extend** |
| 3d | Ad-text checker: phones/links cut, numbers only from sources, age only 18+, no gender/appearance/nationality/religion, no false positives on "2 years of experience" / "attractive salary" | Partly: `recruiting._clean` cuts phones/links in template fields; `find_banned` drops bullet lines (no number check, no 18+ rule, no appearance/religion patterns for ads, `\d{2} years` flags "10 years of experience") | **extend** (new `check_ad`, used for every free ad text) |
| 3e | "Task for the agent" queue with human apply (panel) | No | **add** |
| 3f | Publish only on HR's explicit word | Partly: bot regex `VAC_PUBLISH` matches inside longer phrases, so "e'lon qilma" / "не опубликуй" would publish | **extend** (whole-message confirm word, checked in code) |
| 4a | Invite / reject with a preview of the exact candidate message | Partly: `hiring.invite` sends slots (no preview); reject = status only, no message (`recruiting.set_status`) | **extend** |
| 4b | Outbox sent at most once | Partly: `bots/main.py:send_outbox` marks `sent_at` after a batch; a crash between send and commit re-sends; no dedupe of double clicks | **extend** (claim before send, dedupe key) |
| 4c | Interview slots | Yes: `InterviewSlot`, `api/hiring.py` `/api/slots`, `Hiring.tsx` | skip |
| 4d | Free-text booking mapped by the model to an offered slot only; atomic booking; reschedule / cancel by text | Partly: number-only answer (`hiring.answer`), check-then-set booking (not atomic), no reschedule / cancel by text | **extend** |
| 4e | Reminders day before 18:00 and 1 h before | Partly: one reminder ~2 h before (`hiring.remind`) | **extend** |
| 4f | Job offer in words → employee card | Yes: `hiring.offer` / `_hire` | skip |
| 5 | Hire → onboarding handoff (waiting list, one-click employee + plan, dismiss with reason, waiting count in the onboarding report) | Partly: an accepted offer creates the card + course (`hiring._hire`). A candidate marked *hired* in the panel / Mini App (`recruiting.set_status`) gets nothing — no waiting list, no dismiss, no count in `topic_reports.onboarding_md` | **extend** |
| 6a | Payroll: tabel-close reminder from the 1st until closed | No (`notifications.collect` only has the payday pre-check) | **add** |
| 6b | Weekly per-branch signals (last 7 days vs previous 4 weeks, ≥ 2× and ≥ 3; groups count-only, per-branch only in private) | No (`topic_reports.analytics_md` has network-wide 4-week trends, no per-branch signals) | **add** |

Product-rule notes found while porting:
- The Telegram channel post used an inline URL button ("Ariza topshirish"); the ad text already carries the apply link, so the
  button is removed (agents and their posts use plain text only).
