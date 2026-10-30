"""New HR agent tools: discipline ranking, one employee's month, payroll summary (payroll-gated)."""
import json

from app.agents.registry import AGENTS
from app.agents.tools import TOOLS, Ctx, execute, tools_for
from app.models import Employee
from app.rbac import Scope
from sqlalchemy import select

OWNER = Scope("tg:1", "owner", None, True)


def test_discipline_and_employee_month(db):
    out = json.loads(execute(Ctx(db, OWNER, "hamza"), TOOLS["discipline_ranking"], {}))
    assert out["rows"] and "late_days" in out["rows"][0]
    e = db.scalar(select(Employee).where(Employee.status != "fired"))
    m = json.loads(execute(Ctx(db, OWNER, "hamza"), TOOLS["employee_month"], {"employee_id": e.id}))
    assert m["full_name"] == e.full_name and "days" in m


def test_payroll_summary_needs_payroll_visibility():
    no_pay = Scope("tg:2", "hr_head", None, False)
    names = {t.name for t in tools_for(AGENTS["bexruz"].tools, no_pay)}
    assert "payroll_summary" not in names and "discipline_ranking" in names
    assert "payroll_summary" in {t.name for t in tools_for(AGENTS["bexruz"].tools, OWNER)}
