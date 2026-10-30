"""Weekly discipline reminders: drafts for people late >= N days last week. Never sent without HR approval."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import cfg
from ..models import Employee, Nudge, Outbox
from ..rbac import Scope, audit
from . import weekly


def draft_week(db: Session, scope: Scope, monday: date | None = None) -> list[Nudge]:
    monday = monday or date.today() - timedelta(days=date.today().weekday() + 7)
    w = weekly.week_data(db, scope, monday)
    min_days = int(cfg("discipline.nudge_min_late_days", 2))
    made = []
    for p in w["people"]:
        if p["late"] < min_days:
            continue
        e = db.get(Employee, p["id"])
        if not e or not e.telegram_id or db.scalar(select(Nudge).where(Nudge.employee_id == e.id, Nudge.week == monday.isoformat())):
            continue
        parts = e.full_name.split()
        first = parts[1] if len(parts) > 1 else e.full_name
        text = (f"Assalomu alaykum, {first}!\n\nO'tgan hafta ({monday:%d.%m}–{monday + timedelta(days=6):%d.%m}) "
                f"{p['late']} kun kechikdingiz, jami {p['late_min']} daqiqa. Iltimos, ish vaqtiga e'tibor bering.\n"
                "Sababi bo'lsa — shu yerga yozing.")
        n = Nudge(employee_id=e.id, week=monday.isoformat(), late_days=p["late"], late_min=p["late_min"], text=text)
        db.add(n)
        made.append(n)
    db.flush()
    return made


def send(db: Session, scope: Scope, ids: list[int]) -> int:
    sent = 0
    for n in db.scalars(select(Nudge).where(Nudge.id.in_(ids), Nudge.status == "draft")):
        if n.employee.branch_id and not scope.allows_branch(n.employee.branch_id):
            continue
        db.add(Outbox(telegram_id=n.employee.telegram_id, text=n.text))
        n.status, n.decided_by = "sent", scope.actor
        sent += 1
    audit(db, scope, "nudges_send", None, count=sent)
    return sent
