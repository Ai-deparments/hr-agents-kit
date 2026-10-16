from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.agents.registry import route
from app.agents.runtime import run_agent
from app.agents.tools import TOOLS, Ctx, tools_for
from app.models import AttendanceEvent, Branch, Employee, HrOverride, LeadReport, OnboardingPlan, Position
from app.rbac import Scope, scope_for_telegram
from app.services import analytics, attendance as att, onboarding, payroll, people, recruiting

OWNER = Scope("test", "owner", None, True)


def _new_emp(db, sched="sutki_1_2", salary=6_000_000, branch_code="P01"):
    b = db.scalar(select(Branch).where(Branch.code == branch_code))
    p = db.scalar(select(Position).where(Position.code == "pharmacist"))
    e = Employee(full_name="Test Person", branch_id=b.id, position_id=p.id, hire_date=date(2026, 1, 1),
                 schedule_code=sched, schedule_anchor=date(2026, 1, 1), base_salary=salary, leave_balance_days=5)
    db.add(e)
    db.flush()
    return e


def _workday(e, start=date(2026, 3, 1)):
    from app.services import schedules
    d = start
    while not schedules.is_workday(e, d):
        d += timedelta(days=1)
    return d


def test_overnight_24h_shift_counts_once(db):
    e = _new_emp(db)
    d = _workday(e)
    db.add_all([AttendanceEvent(employee_id=e.id, kind="in", ts=datetime.combine(d, datetime.min.time()) + timedelta(hours=8)),
                AttendanceEvent(employee_id=e.id, kind="out", ts=datetime.combine(d, datetime.min.time()) + timedelta(hours=32))])
    db.flush()
    data = att.AttendanceData(db, [e.id], d, d + timedelta(days=1))
    r = att.compute_day(e, d, data, now=datetime(2026, 4, 1))
    assert r.status == "present" and r.worked_hours == 24
    assert att.compute_day(e, d + timedelta(days=1), data, now=datetime(2026, 4, 1)).status == "off"


def test_missing_checkout_is_review_not_8h(db):
    e = _new_emp(db, "day_9_18")
    d = _workday(e)
    db.add(AttendanceEvent(employee_id=e.id, kind="in", ts=datetime.combine(d, datetime.min.time()) + timedelta(hours=9)))
    db.flush()
    data = att.AttendanceData(db, [e.id], d, d)
    assert att.compute_day(e, d, data, now=datetime.combine(d, datetime.min.time()) + timedelta(hours=12)).status == "on_shift"
    r = att.compute_day(e, d, data, now=datetime(2026, 4, 1))
    assert r.status == "needs_review" and r.worked_hours is None


def test_unmarked_is_not_absent_and_priorities(db):
    e = _new_emp(db, "day_9_18")
    d = _workday(e)
    data = att.AttendanceData(db, [e.id], d, d)
    assert att.compute_day(e, d, data, now=datetime(2026, 4, 1)).status == "unmarked"
    db.add(AttendanceEvent(employee_id=e.id, kind="in", ts=datetime.combine(d, datetime.min.time()) + timedelta(hours=9)))
    db.add(LeadReport(employee_id=e.id, day=d, status="absent"))
    db.flush()
    assert att.compute_day(e, d, att.AttendanceData(db, [e.id], d, d), now=datetime(2026, 4, 1)).status == "conflict"
    t = datetime.combine(d, datetime.min.time())
    db.add(HrOverride(employee_id=e.id, day=d, check_in=t + timedelta(hours=9), check_out=t + timedelta(hours=18), reason="fix", author="hr"))
    db.flush()
    r = att.compute_day(e, d, att.AttendanceData(db, [e.id], d, d), now=datetime(2026, 4, 1))
    assert r.source == "hr" and r.status == "present" and r.worked_hours == 8


def test_late_detection_uses_personal_schedule(db):
    e = _new_emp(db, "day_9_18")
    d = _workday(e)
    t = datetime.combine(d, datetime.min.time())
    db.add_all([AttendanceEvent(employee_id=e.id, kind="in", ts=t + timedelta(hours=9, minutes=25)),
                AttendanceEvent(employee_id=e.id, kind="out", ts=t + timedelta(hours=18))])
    db.flush()
    r = att.compute_day(e, d, att.AttendanceData(db, [e.id], d, d), now=datetime(2026, 4, 1))
    assert r.status == "late" and r.late_min == 25


def test_branch_scope_is_enforced_in_code(db):
    p1 = db.scalar(select(Branch).where(Branch.code == "P01"))
    p2_emp = db.scalar(select(Employee).join(Branch).where(Branch.code == "P02"))
    head = Scope("tg:1", "manager", {p1.id})
    assert all(r["branch"] == p1.name for r in people.search_employees(db, head, ""))
    with pytest.raises(people.AccessDenied):
        people.employee_card(db, head, p2_emp)
    s = att.day_summary(db, head, date.today())
    assert set(s["by_branch"]) <= {p1.name}


def test_tg_roles(db):
    assert scope_for_telegram(db, 9999).role == "owner"
    head = scope_for_telegram(db, 1001)
    assert head.role == "manager" and len(head.branch_ids) == 1
    regional = scope_for_telegram(db, 1004)
    assert regional.role == "manager" and len(regional.branch_ids) == 2
    assert scope_for_telegram(db, 2001).role == "employee"
    assert scope_for_telegram(db, 123456).role == "guest"


def test_tools_hidden_above_role():
    manager = Scope("m", "manager", {1}, payroll=False)
    names = {t.name for t in tools_for(list(TOOLS), manager)}
    assert "payroll_precheck" not in names and "onboarding_add" not in names
    hr_no_pay = Scope("h", "hr_head", None, payroll=False)
    assert "payroll_precheck" not in {t.name for t in tools_for(list(TOOLS), hr_no_pay)}


def test_onboarding_plan_self_only(db):
    plan = db.scalar(select(OnboardingPlan))
    other = db.scalar(select(Employee).where(Employee.id != plan.employee_id, Employee.status != "fired"))
    me = Scope("tg:x", "employee", {other.branch_id}, employee_id=other.id)
    res = TOOLS["my_onboarding_plan"].fn(Ctx(db, me, "suhayl"))
    assert res.get("employee_id") != plan.employee_id
    # the employee tool has no argument to ask for someone else
    assert TOOLS["my_onboarding_plan"].params == {}


def test_onboarding_progress_and_score(db):
    e = _new_emp(db, "day_9_18")
    plan = onboarding.create_plan(db, OWNER, e, mentor="Head")
    assert plan.items, "template checklist created"
    onboarding.mark_item(db, OWNER, plan.items[0].id)
    assert onboarding.record_score(db, OWNER, plan, 55)["label"].startswith("low")
    with pytest.raises(onboarding.NotAllowed):
        onboarding.create_plan(db, Scope("m", "manager", None), _new_emp(db))


def test_vacation_balance_and_approval_to_tabel(db):
    e = _new_emp(db, "day_9_18")
    with pytest.raises(ValueError):
        people.create_request(db, OWNER, e, "vacation", date(2026, 3, 2), date(2026, 3, 10))
    r = people.create_request(db, OWNER, e, "vacation", date(2026, 3, 2), date(2026, 3, 4))
    with pytest.raises(people.AccessDenied):
        people.decide_request(db, Scope("agent:suhayl", "owner"), r.id, True, "ok")
    people.decide_request(db, OWNER, r.id, True, "approved by head")
    db.flush()
    res = att.compute_day(e, date(2026, 3, 3), att.AttendanceData(db, [e.id], date(2026, 3, 3), date(2026, 3, 3)))
    assert res.status == "leave" and e.leave_balance_days == 2


def test_payroll_formula_and_visibility(db):
    month = date.today().strftime("%Y-%m")
    full = payroll.payroll_table(db, OWNER, month)
    known = [r for r in full["rows"] if r["known"]]
    assert known and all(isinstance(r["total"], int) for r in known)
    assert any(not r["known"] and r["total"] is None for r in full["rows"]), "unknown salary shown as None, not 0"
    hidden = payroll.payroll_table(db, Scope("hr", "hr_manager", None, payroll=False), month)
    assert all(r["total"] is None and r["base"] is None for r in hidden["rows"]) and hidden["fund"] is None
    pc = payroll.precheck(db, OWNER, month)
    assert pc["count"] >= 1 and any(i["type"] == "no_contract_salary" for i in pc["issues"])


def test_interview_scoring_rules():
    s = recruiting.score_candidate({"role_fit": {"score": 90, "comment": "x"}, "specifics": {"score": 80, "comment": "y"},
                                    "communication": {"score": 60, "comment": "z"}, "motivation": {"score": 50, "comment": "w"}})
    assert s["score"] == round((90 * 40 + 80 * 25 + 60 * 15 + 50 * 20) / 100) and s["status"] == "shortlist"
    no_comment = recruiting.score_candidate({"role_fit": {"score": 10}, "motivation": {"score": 90, "comment": "ok"}})
    assert no_comment["used"] == ["motivation"]
    assert recruiting.score_candidate({})["status"] == "new"
    assert recruiting.find_banned("Are you married? Сколько вам лет и есть ли дети?")
    assert not recruiting.find_banned("Do you have a valid pharmacist certificate?")


def test_new_candidate_with_high_score_goes_to_shortlist():
    from app.models import Candidate
    c = Candidate(full_name="X")  # not flushed: status is still None
    good = {k: {"score": 90, "comment": "ok"} for k in ("role_fit", "specifics", "communication", "motivation")}
    recruiting.apply_score(None, c, good)
    assert c.status == "shortlist"
    c.status = "rejected"
    recruiting.apply_score(None, c, good)
    assert c.status == "rejected", "scoring never overrides a human decision"


def test_small_group_percent_rule():
    assert analytics.pct(1, 3).endswith("(% unreliable)")
    assert analytics.pct(2, 8) == "2 of 8"
    assert analytics.pct(5, 50).startswith("10.0%")


def test_agent_offline_and_refusal(db):
    manager = scope_for_telegram(db, 1001)
    assert "came" in run_agent(db, "hamza", manager, "/hisobot", "t1")
    emp = scope_for_telegram(db, 2001)
    assert "managers" in run_agent(db, "hamza", emp, "hello", "t2")
    assert "Your Telegram ID" not in run_agent(db, "suhayl", emp, "/menu", "t3")


def test_hub_routing():
    assert route("сколько у меня отпуска") == "suhayl"
    assert route("payroll check please") == "bexruz"
    assert route("@husayn turnover") == "husayn"
