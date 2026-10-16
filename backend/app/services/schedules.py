"""Shift schedules: fixed weekdays, 2/2, 24/48 (sutki) — incl. shifts that cross midnight."""
from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta

from ..config import cfg
from ..models import Employee


def schedule(code: str) -> dict:
    return (cfg("schedules", {}) or {}).get(code) or {"type": "fixed", "start": "09:00", "hours": 8, "lunch_min": 60, "weekdays": [0, 1, 2, 3, 4]}


def holidays() -> set[date]:
    return {date.fromisoformat(str(x)) for x in (cfg("calendar.holidays", []) or [])}


def is_workday(emp: Employee, d: date) -> bool:
    s = schedule(emp.schedule_code)
    if s["type"] == "cycle":
        anchor = emp.schedule_anchor or date.fromisoformat(str(s.get("anchor", "2026-01-01")))
        pattern = s["pattern"]
        return bool(pattern[(d - anchor).days % len(pattern)])
    return d.weekday() in s.get("weekdays", [0, 1, 2, 3, 4]) and d not in holidays()


def planned_start(emp: Employee, d: date) -> datetime | None:
    if not is_workday(emp, d):
        return None
    hh, mm = map(int, schedule(emp.schedule_code)["start"].split(":"))
    return datetime.combine(d, time(hh, mm))


def planned_hours(emp: Employee, d: date) -> float:
    return float(schedule(emp.schedule_code)["hours"]) if is_workday(emp, d) else 0.0


def lunch_hours(emp: Employee) -> float:
    return schedule(emp.schedule_code).get("lunch_min", 0) / 60


def month_days(month: str) -> list[date]:
    y, m = map(int, month.split("-"))
    return [date(y, m, i) for i in range(1, calendar.monthrange(y, m)[1] + 1)]


def employed_on(emp: Employee, d: date) -> bool:
    if emp.hire_date and d < emp.hire_date:
        return False
    if emp.fire_date and d > emp.fire_date:
        return False
    return True


def norm_hours(emp: Employee, month: str) -> float:
    """Norm comes from the person's own schedule, not a company-wide calendar."""
    return sum(planned_hours(emp, d) for d in month_days(month) if employed_on(emp, d))


SHIFT_WINDOW = timedelta(hours=int(cfg("attendance.needs_review_after_hours", 30)))


def window_end(d: date) -> datetime:
    """Latest moment a check-out for a shift starting on day d can arrive (24h shift from late start + slack)."""
    return datetime.combine(d, time()) + timedelta(hours=48)
