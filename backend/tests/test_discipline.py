"""Discipline rules: admin-only edits with audit, warnings -> fine, snapshot amounts."""
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, DisciplineRule, Employee, PayrollEntry
from app.rbac import Scope
from app.services import discipline

c = TestClient(app)
ADMIN = Scope("user:admin", "admin", None, True, None, {"*"})


def _h(u, p="demo12345"):
    return {"Authorization": f"Bearer {c.post('/api/auth/login', json={'username': u, 'password': p}).json()['token']}"}


def _emp(db):
    return db.scalar(select(Employee).where(Employee.status != "fired").order_by(Employee.id.desc()))


def test_rules_seeded_from_config_and_listed():
    r = c.get("/api/discipline/rules", headers=_h("hr")).json()
    assert {x["code"] for x in r["rules"]} >= {"late", "no_show", "cash_shortage"} and r["can_edit"] is False
    assert c.get("/api/discipline/rules", headers=_h("admin", "admin12345")).json()["can_edit"] is True


def test_only_admin_edits_and_no_add_or_delete(db):
    rule = db.scalar(select(DisciplineRule).where(DisciplineRule.code == "late"))
    assert c.patch(f"/api/discipline/rules/{rule.id}", json={"fine_amount": 1}, headers=_h("hr")).status_code == 403
    assert c.post("/api/discipline/rules", json={"code": "x", "title": "x"}, headers=_h("admin", "admin12345")).status_code in (404, 405)
    assert c.delete(f"/api/discipline/rules/{rule.id}", headers=_h("admin", "admin12345")).status_code in (404, 405)
    assert c.patch(f"/api/discipline/rules/{rule.id}", json={"window": "weekly"}, headers=_h("admin", "admin12345")).status_code == 400
    r = c.patch(f"/api/discipline/rules/{rule.id}", json={"text": "Coming after the grace time.", "note": "n", "warnings_before_fine": 2},
                headers=_h("admin", "admin12345"))
    assert r.status_code == 200 and r.json()["text"] == "Coming after the grace time."
    log = db.scalar(select(AuditLog).where(AuditLog.action == "discipline_rule_update").order_by(AuditLog.id.desc()))
    assert log.details["after"]["text"] == {"len": len("Coming after the grace time.")}  # texts are logged as lengths
    assert "Coming" not in str(log.details)


def test_warnings_then_fine_and_snapshot(db):
    emp = _emp(db)
    rule = db.scalar(select(DisciplineRule).where(DisciplineRule.code == "no_show"))  # all_time, 1 warning
    rule.warnings_before_fine, rule.fine_amount, rule.extra_amount, rule.starts_on = 1, 200_000, 12_000, None
    month = date.today().strftime("%Y-%m")
    first = discipline.apply_rule(db, ADMIN, emp, rule, month, "did not come, no call")
    second = discipline.apply_rule(db, ADMIN, emp, rule, month, "again")
    assert (first.outcome, second.outcome) == ("warning", "fine")
    entry = db.get(PayrollEntry, second.entry_id)
    assert entry.kind == "penalty" and entry.amount == 212_000
    discipline.update_rule(db, ADMIN, rule, {"fine_amount": 999_999})
    db.flush()
    assert db.get(PayrollEntry, second.entry_id).amount == 212_000 and second.fine_amount == 200_000  # snapshot kept
    db.rollback()


def test_cancelled_case_does_not_count_and_per_case_always_fines(db):
    emp = _emp(db)
    month = date.today().strftime("%Y-%m")
    late = db.scalar(select(DisciplineRule).where(DisciplineRule.code == "late"))
    late.window, late.warnings_before_fine, late.starts_on = "month", 1, None
    w = discipline.apply_rule(db, ADMIN, emp, late, month, "15 min late")
    db.get(PayrollEntry, w.entry_id).cancelled = True
    db.flush()
    assert discipline.apply_rule(db, ADMIN, emp, late, month, "late again").outcome == "warning"
    cash = db.scalar(select(DisciplineRule).where(DisciplineRule.code == "cash_shortage"))
    cash.window, cash.warnings_before_fine = "per_case", 3
    assert discipline.apply_rule(db, ADMIN, emp, cash, month, "short 20 000").outcome == "fine"
    db.rollback()


def test_apply_is_human_only_and_scoped(db):
    emp = _emp(db)
    rule = db.scalar(select(DisciplineRule))
    import pytest
    with pytest.raises(PermissionError):
        discipline.apply_rule(db, Scope("agent:external", "hr_head", None), emp, rule, "2026-10", "x" * 5)
    with pytest.raises(PermissionError):
        discipline.apply_rule(db, Scope("u", "manager", {-5}), emp, rule, "2026-10", "x" * 5)
    r = c.post("/api/discipline/apply", json={"employee_id": emp.id, "rule_id": rule.id, "month": "2026-01", "reason": "late"},
               headers=_h("regional"))
    assert r.status_code in (403, 404)
    db.rollback()


def test_apply_via_api_and_cases_list(db):
    emp = _emp(db)
    rule = db.scalar(select(DisciplineRule).where(DisciplineRule.code == "late"))
    month = date.today().strftime("%Y-%m")
    r = c.post("/api/discipline/apply", json={"employee_id": emp.id, "rule_id": rule.id, "month": month, "reason": "25 min late"},
               headers=_h("hr"))
    assert r.status_code == 200 and r.json()["outcome"] in ("warning", "fine")
    rows = c.get(f"/api/discipline/cases?month={month}", headers=_h("hr")).json()
    assert any(x["reason"] == "25 min late" for x in rows)
    assert all(x["amount"] is None for x in rows if x["outcome"] == "fine")  # hr without payroll right sees no money


def test_hr_agent_reads_rules_but_cannot_apply(db):
    import json
    from app.agents.registry import AGENTS
    from app.agents.tools import TOOLS, Ctx, execute
    assert "discipline_rules" in AGENTS["hr"].tools
    out = json.loads(execute(Ctx(db, Scope("tg:1", "hr_head", None, False), "hr"), TOOLS["discipline_rules"], {}))
    assert {r["code"] for r in out} >= {"late", "no_show"} and "updated_by" not in out[0]
    assert not any("apply" in n and "discipline" in n for n in TOOLS)  # applying a rule stays a human action
