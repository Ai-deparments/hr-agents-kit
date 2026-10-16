---
name: security-audit
description: >
  Run a security review of a project (any project, new or old — not tied to
  one repo). Use whenever the user asks to "check for vulnerabilities / holes",
  "проверь дыры / безопасность", "pentest this", "audit the code", "sca / dast /
  sast", mentions Strix, or asks to security-check a project before shipping /
  after finishing a feature / on first setup. Drives the Strix autonomous
  pentest tool when it is installed, and always also runs a manual review
  checklist so the audit is useful even without Strix.
---

# Security Audit

Goal: find real, exploitable weaknesses in **the user's own** project and fix
the clear ones, leaving a ranked list of the rest.

Only ever run against a target the user owns (their local repo, their GitHub
repo, their deployed app). Never point a scanner at third-party
infrastructure.

## 1. Scope the target

Confirm with the user in one line what to audit:
- a local directory (default: the project in the working directory),
- a GitHub repo URL they own,
- a deployed URL they own.

## 2. Strix (autonomous pentest) — if available

Strix (`github.com/usestrix/strix`) runs the code dynamically and validates
findings with real exploits. It needs **Docker** and an **LLM API key**, and
it **costs API credits** and **executes code** — so get an explicit "yes"
before each run, and never run its `curl | bash` installer yourself.

```bash
command -v strix            # is it installed?
echo "$LLM_API_KEY" "$STRIX_LLM"   # is it configured?
```

- **Not installed** → tell the user once:
  "Strix isn't installed. To enable autonomous scans: install Docker, then
  run `curl -sSL https://strix.ai/install | bash` yourself, and set
  `export STRIX_LLM=...` + `export LLM_API_KEY=...` (OpenRouter/OpenAI/
  Anthropic). Skipping to the manual review."
  Then go to section 3.
- **Installed + configured** → confirm, then:
  ```bash
  strix --target <dir | repo-url | app-url>
  ```
  Results land in `strix_runs/<run-name>`; `strix view` opens the dashboard.
  Read the run output, then continue to section 3 to sanity-check and to
  cover what Strix skipped.

## 3. Manual review checklist (always run this)

Walk the codebase for these. Use Grep/Read, not assumptions.

- **Secrets in git**: `git log --all -p -- '*.env*'`, scan tracked files for
  API keys, tokens, private keys, passwords, seed phrases, connection strings.
  Anything found that is live → tell the user to rotate it; do not print the
  value into chat.
- **Injection**: string-built SQL, shell (`exec`, `child_process`, `os.system`,
  f-strings into `subprocess`), `eval`, template injection, unparameterised
  queries.
- **AuthZ / AuthN**: every route/handler — is there an auth check? Can a user
  reach another user's data by changing an id (IDOR)? Admin endpoints behind a
  real gate? Signature/token verification constant-time?
- **SSRF / open proxy**: user-controlled URLs passed to `fetch`/`axios`/
  `requests`; redirects followed blindly.
- **Input validation**: request bodies validated (zod/pydantic/…)? Numeric
  amounts/quantities bounded? File uploads type/size-checked?
- **Rate limiting**: login, payment, OTP, expensive endpoints.
- **Web**: reflected/stored XSS (unescaped user text in innerHTML/templates),
  CSRF on state-changing routes, permissive CORS (`*` with credentials),
  missing security headers.
- **Money paths** (payment/fulfilment/ledger): double-spend, replay, missing
  idempotency, race conditions on balance updates, retry that re-charges.
- **Dependencies**: `npm audit` / `pip-audit` / `osv-scanner` if present;
  note high/critical.
- **Secrets at rest**: cookies/tokens stored plaintext where they could be
  encrypted; overly long session TTLs.
- **Error handling**: stack traces / internal detail leaked to clients.

## 4. Report and fix

- Rank findings: **critical / high / medium / low**, each with file:line, the
  concrete failure scenario, and the fix.
- Fix the unambiguous ones directly (with tests where the project has them).
- Leave findings that need a product decision or the user's infra access as a
  checklist for them.
- If the project has tests/linters, run them after fixes.

## Notes

- This skill is project-agnostic — the same flow applies to a fresh repo or a
  years-old one.
- For a deep, evidence-validated audit (attack classes, coverage ledger, JSON
  report schema) use Cloudflare's methodology, vendored in this repo as
  `cloudflare-security-audit` (`third_party/cloudflare-security-audit`, MIT).
  Run this skill first for the quick pass, that one for the full audit.
