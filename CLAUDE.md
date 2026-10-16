# hr-agents-kit — instructions for AI coding agents

- The stack is fixed: read `.claude/skills/default-stack/SKILL.md` and follow it. Do not ask which framework, DB, bot library or model to use.
- Business rules belong in `config/company.yaml`. Never hard-code a client name, branch or salary rule.
- Every service takes a `Scope`. A new agent tool must declare `min_role` (and `needs_payroll` if it touches money).
- Agents never perform the 7 human-only actions. They call `request_human_action`.
- Run `cd backend; .venv\Scripts\python -m pytest -q` and `cd web; npm run build` after changes.
- Before shipping, run the `security-audit` skill; for a deep audit, also run `cloudflare-security-audit`.
- READMEs are in Uzbek + Russian (`README.md`); the English version is in `README.en.md`.
