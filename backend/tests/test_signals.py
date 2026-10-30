"""Payroll tabel-close reminder; weekly per-branch signals (group: count only; private: per branch)."""
from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.models import AttendanceEvent, Branch, Employee, LeadReport, PeriodStatus, Position
from app.rbac import Scope
from app.services import analytics, notifications, schedules, topic_reports

OWNER = Scope("test", "owner", None, True)


def test_tabel_close_reminder_until_closed(db):
    today = date.today().replace(day=3)
    prev = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    notes = [n for n in notifications.collect(db, today) if n.kind == "tabel_close"]
    assert len(notes) == 1 and notes[0].target == "tabel_closers" and prev in notes[0].text and "Ochiq masalalar" in notes[0].text
    assert "UZS" not in notes[0].text and "so'm" not in notes[0].text  # counts by type, no money
    db.rollback()
    p = db.get(PeriodStatus, prev) or PeriodStatus(month=prev)
    p.tabel_closed = True
    db.add(p)
    db.flush()
    assert not [n for n in notifications.collect(db, today) if n.kind == "tabel_close"]
    db.rollback()


def _branch_with_staff(db, code="SIG"):
    b = db.scalar(select(Branch).where(Branch.code == code))
    if not b:
        b = Branch(code=code, name="Signal Branch", city="Test")
        db.add(b)
        db.flush()
    pos = db.scalar(select(Position).where(Position.code == "cashier"))
    staff = []
    for i in range(3):
        e = Employee(full_name=f"Signal Person {i}", branch_id=b.id, position_id=pos.id, hire_date=date(2025, 1, 1),
                     schedule_code="day_9_18")
        db.add(e)
        staff.append(e)
    db.flush()
    return b, staff


def test_weekly_signals_threshold_and_privacy(db):
    today = date.today()
    b, staff = _branch_with_staff(db)
    days = [d for d in (today - timedelta(days=i) for i in range(1, 7)) if schedules.is_workday(staff[0], d)][:4]
    for e, d in zip(staff + staff, days):  # 3+ late arrivals this week, none before
        t = datetime.combine(d, datetime.min.time())
        db.add_all([AttendanceEvent(employee_id=e.id, kind="in", ts=t + timedelta(hours=9, minutes=40)),
                    AttendanceEvent(employee_id=e.id, kind="out", ts=t + timedelta(hours=18, minutes=5))])
    for d in [days[0], days[1], days[3]]:  # confirmed absences this week (staff[2] has no check-in on these days)
        db.add(LeadReport(employee_id=staff[2].id, day=d, status="absent"))
    db.flush()
    scope = Scope("tg:x", "manager", {b.id})
    w = analytics.weekly_signals(db, scope, today)
    metrics = {s["metric"] for s in w["signals"]}
    assert "late" in metrics and "absent" in metrics and all(s["branch"] == "Signal Branch" for s in w["signals"])
    group = topic_reports.weekly_signals_md(db, scope, today)
    private = topic_reports.weekly_signals_md(db, scope, today, private=True)
    assert "Signal Branch" not in group and f"**{len(w['signals'])}**" in group
    assert "Signal Branch" in private and "kechikish" in private
    assert topic_reports.weekly_signals_md(db, Scope("tg:y", "manager", {-1}), today) is None  # nothing -> no message
    db.rollback()


def test_weekly_signals_need_two_times_usual(db):
    today = date.today()
    b, staff = _branch_with_staff(db, "SIG2")
    e = staff[0]
    week = [d for d in (today - timedelta(days=i) for i in range(0, 35)) if schedules.is_workday(e, d)]
    for d in week:  # late every working day: this week is not 2x the usual week
        t = datetime.combine(d, datetime.min.time())
        db.add_all([AttendanceEvent(employee_id=e.id, kind="in", ts=t + timedelta(hours=9, minutes=40)),
                    AttendanceEvent(employee_id=e.id, kind="out", ts=t + timedelta(hours=18, minutes=10))])
    db.flush()
    w = analytics.weekly_signals(db, Scope("tg:x", "manager", {b.id}), today)
    assert not [s for s in w["signals"] if s["metric"] == "late"]
    db.rollback()


def test_early_leave_detection(db):
    b, staff = _branch_with_staff(db, "SIG3")
    e = staff[0]
    d = next(x for x in (date.today() - timedelta(days=i) for i in range(1, 10)) if schedules.is_workday(e, x))
    t = datetime.combine(d, datetime.min.time())
    db.add_all([AttendanceEvent(employee_id=e.id, kind="in", ts=t + timedelta(hours=9)),
                AttendanceEvent(employee_id=e.id, kind="out", ts=t + timedelta(hours=16))])
    db.flush()
    from app.services import attendance as att
    res = att.compute_day(e, d, att.AttendanceData(db, [e.id], d, d))
    assert analytics._early_leave(e, d, res) is True
    db.rollback()


def test_tabel_reminder_goes_only_to_tabel_closers_and_agent_tool(db):
    import json
    from app.agents.registry import AGENTS
    from app.agents.tools import TOOLS, Ctx, execute
    assert "weekly_signals" in AGENTS["hr"].tools
    out = json.loads(execute(Ctx(db, OWNER, "hr"), TOOLS["weekly_signals"], {}))
    assert out["rule"].startswith(">= 3") and "signals" in out
    notes = notifications.collect(db, date.today().replace(day=2))
    assert all(n.target == "tabel_closers" for n in notes if n.kind == "tabel_close")
    db.rollback()
