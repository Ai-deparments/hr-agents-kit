"""TimePay import with a fake API: people, salary, check-ins; second run adds nothing."""
from datetime import date

import httpx
from sqlalchemy import select

from app.importers import timepay
from app.models import AttendanceEvent, Employee, ExternalRef, PayrollEntry


def _api(request: httpx.Request) -> httpx.Response:
    assert request.headers["Authorization"] == "Bearer tp_test"
    p = request.url.path.split("/integration/")[1]
    today = date.today().isoformat()
    data = {
        "branches/": [{"id": 1, "name": "Bosh ofis TP", "is_main": True}],
        "departments/": [{"id": 5, "name": "Marketing TP"}],
        "positions/": [{"id": 7, "name": "SMM TP"}],
        "salary/monthly/": [{"employee_id": 100, "assigned_salary": "9000000.00", "salary_type": "MONTHLY"}],
        "schedules/": [{"id": 38, "work_days": [{"day": d, "is_working": True, "start_time": "09:00:00", "end_time": "18:00:00",
                                                 "break_start": "13:00:00", "break_end": "14:00:00"} for d in range(1, 7)],
                        "employee_ids": [100]}],
        "fines/": [{"id": 7001, "employee": {"id": 100}, "amount": 25000, "amount_type": "AMOUNT", "fine_type": "LATE",
                    "reason": "Kechikish", "date": f"{today}T09:18:00+05:00"},
                   {"id": 7002, "employee": {"id": 100}, "amount": 1, "amount_type": "PERCENT", "fine_type": "OTHER",
                    "reason": "Intizom", "date": f"{today}T10:00:00+05:00"}] if request.url.params.get("month") == str(date.today().month) else [],
        "bonuses/": [{"id": 3001, "employee": {"id": 100}, "amount": "500000.00", "type": "PERFORMANCE", "date": today,
                      "description": "Reja bajarildi"}] if request.url.params.get("month") == str(date.today().month) else [],
        "deductions/": [{"id": 4001, "employee": {"id": 100}, "amount": "120000.00", "date": today, "description": "",
                         "is_unpaid_leave": True}] if request.url.params.get("month") == str(date.today().month) else [],
        "employees/": [{"id": 100, "first_name": "Ali", "last_name": "Valiyev", "phone_number": "+998901234567",
                        "position": {"id": 7, "name": "SMM TP"}, "department": {"id": 5, "name": "Marketing TP"},
                        "branches": [{"id": 1, "name": "Bosh ofis TP"}], "work_start_date": "2026-01-15",
                        "resigned_at": None, "is_active": True}],
        "checkinouts/": [] if request.url.params.get("date") != today else [
            {"id": 9001, "employee": {"id": 100}, "action": "IN", "status": "LATE", "source": "FACE_ID",
             "created_at": f"{today}T04:12:00Z", "late_minutes": 12},
            {"id": 9002, "employee": {"id": 100}, "action": "OUT", "status": None, "source": "FACE_ID",
             "created_at": f"{today}T13:05:00Z", "late_minutes": 0},
            {"id": 9003, "employee": {"id": 100}, "action": "IN", "status": "REJECTED", "source": "GPS",
             "created_at": f"{today}T05:00:00Z", "late_minutes": 0}],
    }[p]
    return httpx.Response(200, json={"results": data, "next": None})


def test_timepay_sync_idempotent(db):
    t = httpx.MockTransport(_api)
    s1 = timepay.sync(3, token="tp_test", transport=t)
    assert s1["employees_new"] == 1 and s1["checkins_new"] == 2  # rejected check-in skipped
    assert s1["money_new"] == 4  # 2 fines (one is 1% of 9M), bonus, unpaid-leave deduction
    s2 = timepay.sync(3, token="tp_test", transport=t)
    assert s2["employees_new"] == 0 and s2["checkins_new"] == 0 and s2["employees_updated"] == 0 and s2["money_new"] == 0
    eid = db.scalar(select(ExternalRef.local_id).where(ExternalRef.source == "timepay", ExternalRef.kind == "employee"))
    e = db.get(Employee, eid)
    assert e.full_name == "Ali Valiyev" and e.base_salary == 9_000_000 and e.pay_type == "monthly"
    assert e.department.name == "Marketing TP" and e.position.title == "SMM TP" and e.hire_date == date(2026, 1, 15)
    ev = list(db.scalars(select(AttendanceEvent).where(AttendanceEvent.employee_id == eid).order_by(AttendanceEvent.ts)))
    assert [x.kind for x in ev] == ["in", "out"] and ev[0].verified == "face"
    assert ev[0].ts.hour == 9 and ev[0].ts.minute == 12  # 04:12 UTC -> 09:12 Tashkent
    assert e.schedule_code == "day_6x"  # Mon–Sat 09–18 with a 1 h break
    money = {(x.kind, x.amount) for x in db.scalars(select(PayrollEntry).where(PayrollEntry.employee_id == eid))}
    assert {("penalty", 25000), ("penalty", 90000), ("bonus", 500000), ("other", 120000)} <= money
