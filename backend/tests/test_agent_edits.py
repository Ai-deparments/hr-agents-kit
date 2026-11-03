"""HR edits in words: propose -> confirm from a later message; rights; one person's pay."""
import json
from datetime import date

from sqlalchemy import select

from app.agents.registry import AGENTS
from app.agents.tools import TOOLS, Ctx, execute, tools_for
from app.models import Employee, PayrollEntry
from app.rbac import Scope

HR = Scope("tg:7101", "hr_head", None, True)


def run(db, name, args, scope=HR, ctx=None):
    return json.loads(execute(ctx or Ctx(db, scope, "hr"), TOOLS[name], args))


def _probation(db):
    return db.scalars(select(Employee).where(Employee.status == "probation")).first()


def test_remove_probation_needs_confirm_in_next_message(db):
    e = _probation(db)
    first = Ctx(db, HR, "hr")
    out = run(db, "employee_change", {"employee": f"#{e.id}", "status": "active"}, ctx=first)
    assert out["changes"][0]["field"] == "status" and out["change_id"]
    db.refresh(e)
    assert e.status == "probation"  # nothing saved yet
    same_run = run(db, "confirm_change", {"change_id": out["change_id"]}, ctx=first)
    assert "error" in same_run  # the model cannot confirm its own proposal in one go
    assert "error" in run(db, "confirm_change", {"change_id": "nope00"})
    done = run(db, "confirm_change", {"change_id": out["change_id"]})  # next message = new run
    assert done["applied"] is True
    db.refresh(e)
    assert e.status == "active"
    assert "error" in run(db, "confirm_change", {"change_id": out["change_id"]})  # used once


def test_name_lookup_ambiguity_and_bad_values(db):
    e = db.scalars(select(Employee).where(Employee.status != "fired")).first()
    assert "error" in run(db, "employee_change", {"employee": "zzzz qqqq", "status": "active"})
    assert "error" in run(db, "employee_change", {"employee": f"#{e.id}", "status": "fired"})
    assert "error" in run(db, "employee_change", {"employee": f"#{e.id}", "position": "kosmonavt-xyz"})
    same = run(db, "employee_change", {"employee": f"#{e.id}", "status": e.status})
    assert "error" in same  # nothing would change


def test_payroll_entry_preview_then_saved(db):
    e = db.scalars(select(Employee).where(Employee.status == "active", Employee.base_salary.is_not(None))).first()
    month = date.today().strftime("%Y-%m")
    before = len(list(db.scalars(select(PayrollEntry).where(PayrollEntry.employee_id == e.id))))
    out = run(db, "payroll_entry_add", {"employee": f"#{e.id}", "kind": "advance", "amount": 500000, "reason": "avans so'radi"})
    assert out["changes"][0]["field"] == "advance"
    assert "error" in run(db, "payroll_entry_add", {"employee": f"#{e.id}", "kind": "advance", "amount": 5, "reason": "x"})
    done = run(db, "confirm_change", {})  # no id: the person's last pending change
    assert done["applied"]
    rows = list(db.scalars(select(PayrollEntry).where(PayrollEntry.employee_id == e.id)))
    assert len(rows) == before + 1 and rows[-1].amount == 500000 and rows[-1].month == month


def test_employee_pay_one_person(db):
    e = db.scalars(select(Employee).where(Employee.status == "active", Employee.base_salary.is_not(None))).first()
    out = run(db, "employee_pay", {"employee": f"#{e.id}"})
    assert out["employee"].startswith(f"#{e.id}") and "total" in out and isinstance(out.get("explain"), list)


def test_rights(db):
    names = AGENTS["hr"].tools
    mgr = Scope("tg:5", "manager", None, False)
    have = {t.name for t in tools_for(names, mgr)}
    assert not have & {"employee_change", "payroll_entry_add", "confirm_change", "employee_pay"}
    no_pay = Scope("tg:7102", "hr_head", None, False)
    assert "employee_pay" not in {t.name for t in tools_for(names, no_pay)}
    e = db.scalars(select(Employee).where(Employee.status != "fired")).first()
    assert "error" in run(db, "employee_change", {"employee": f"#{e.id}", "base_salary": 1}, scope=no_pay)
    recruiter_panel = Scope("user:rec", "hr_head", None, False, None, {"recruiting"})  # panel recruiter mapped to hr_head
    assert "error" in run(db, "employee_change", {"employee": f"#{e.id}", "phone": "+998900000000"}, scope=recruiter_panel)


def test_cancel_drops_pending(db):
    e = _probation(db) or db.scalars(select(Employee).where(Employee.status != "fired")).first()
    run(db, "employee_change", {"employee": f"#{e.id}", "phone": "+998901112233"})
    assert run(db, "cancel_change", {})["cancelled"] is True
    assert "error" in run(db, "confirm_change", {})
