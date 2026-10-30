"""Sales agents ranking: ABC split, 80/20, Δ vs previous month, phone-format topic report, role gating."""
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agents.tools import TOOLS, Ctx, execute, tools_for
from app.main import app
from app.models import AuditLog, Branch, Department, Employee, SalesRecord
from app.rbac import Scope
from app.services import sales_kpi, topic_reports

TODAY = date(2031, 3, 15)  # far from the demo data months
MONTH, PREV = "2031-03", "2031-02"
SYS = Scope(actor="t", role="owner")
# 10 agents: 50, 20, 10, 8, 5, 3, 2, 1, 0.6, 0.4 mln = 100 mln
AMOUNTS = [50, 20, 10, 8, 5, 3, 2, 1, 0.6, 0.4]


@pytest.fixture
def sales(db):
    dept = Department(name="Test savdo", description="t")
    db.add(dept)
    db.flush()
    br = db.scalar(select(Branch))
    emps = []
    for i, a in enumerate(AMOUNTS):
        e = Employee(full_name=f"Agent {i + 1:02d}", branch_id=br.id, department_id=dept.id, status="active")
        db.add(e)
        db.flush()
        db.add(SalesRecord(employee_id=e.id, month=MONTH, amount=int(a * 1_000_000)))
        emps.append(e)
    db.add(SalesRecord(employee_id=emps[0].id, month=PREV, amount=40_000_000))  # +25%
    db.add(SalesRecord(employee_id=emps[1].id, month=PREV, amount=25_000_000))  # -20%
    db.flush()
    return dept


def test_abc_pareto_and_delta(db, sales):
    r = sales_kpi.ranking(db, SYS, MONTH, department_id=sales.id, today=TODAY)
    assert r["n"] == 10 and r["total"] == 100_000_000 and r["partial"] is True
    assert [x["class"] for x in r["rows"]] == ["A", "A", "A", "B", "B", "B", "C", "C", "C", "C"]
    assert r["counts"] == {"A": 3, "B": 3, "C": 4}
    assert r["pareto"] == {"top_pct": 20, "top_n": 2, "top_share": 70.0}  # top 2 agents = 70% of sales
    a1, a2, a3 = r["rows"][:3]
    assert (a1["rank"], a1["share"], a1["delta"], a1["delta_pct"]) == (1, 50.0, 10_000_000, 25.0)
    assert a2["delta_pct"] == -20.0
    assert a3["prev_amount"] is None and a3["delta"] is None  # unknown, not 0
    assert r["prev_total"] == 65_000_000 and r["plan"] is None  # department filter / no config -> no plan


def test_scope_filters_branch(db, sales):
    r = sales_kpi.ranking(db, Scope(actor="m", role="manager", branch_ids={-5}), MONTH, department_id=sales.id, today=TODAY)
    assert r["n"] == 0 and r["total"] is None


def test_sales_md(db, sales, monkeypatch):
    assert topic_reports.sales_md(db, SYS, today=date(2031, 7, 1)) is None  # no data that month
    monkeypatch.setattr(sales_kpi, "sales_department_id", lambda _db: sales.id)
    md = topic_reports.sales_md(db, SYS, today=TODAY)
    assert md and "|:-" not in md and "| ---" not in md
    assert md.startswith("## ") and "Agent 01" in md and "Agent 10" in md and "80/20" in md
    assert "A **3** · B **3** · C **4**" in md
    assert topic_reports.sales_md(db, SYS, today=TODAY, evening=True) is None  # nothing imported that day
    db.add(AuditLog(ts=datetime(2031, 3, 15, 9), actor="system", actor_role="system", action="import_smartup",
                    details={"rows": 10, "sales_changed": 0}))
    db.flush()
    assert topic_reports.sales_md(db, SYS, today=TODAY, evening=True) is None  # import ran but nothing changed
    db.add(AuditLog(ts=datetime(2031, 3, 15, 18), actor="system", actor_role="system", action="import_smartup",
                    details={"rows": 10, "sales_changed": 3}))
    db.flush()
    ev = topic_reports.sales_md(db, SYS, today=TODAY, evening=True)
    assert ev and "yangilandi" in ev


def test_tool_role_gating(db, sales):
    emp = Scope(actor="e", role="employee", employee_id=1)
    assert "sales_ranking" not in {t.name for t in tools_for(list(TOOLS), emp)}
    mgr = Scope(actor="m", role="manager")
    assert "sales_ranking" in {t.name for t in tools_for(list(TOOLS), mgr)}
    from app.agents.registry import AGENTS
    assert "sales_ranking" in AGENTS["hr"].tools
    out = execute(Ctx(db, mgr, "hr"), TOOLS["sales_ranking"], {"month": "bad"})
    assert "error" in out


def test_api_permission():
    c = TestClient(app)

    def h(u):
        return {"Authorization": f"Bearer {c.post('/api/auth/login', json={'username': u, 'password': 'demo12345'}).json()['token']}"}
    assert c.get("/api/kpi/sales?month=2031-03", headers=h("hr")).status_code == 200
    assert c.get("/api/kpi/sales?month=2031-3", headers=h("hr")).status_code == 400
    assert c.get("/api/kpi/sales", headers=h("recruiter")).status_code == 403
