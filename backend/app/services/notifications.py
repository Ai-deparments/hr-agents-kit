"""Scheduled triggers (the 'no auto notifications' gap of the original system).
Returns notices; delivery is done by bots/sender.py."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import cfg
from ..models import BranchLead, Employee, LeaveRequest, PulseSent
from ..rbac import Scope
from . import onboarding, payroll, people

SYSTEM = Scope("system", "owner", None, True)


@dataclass
class Notice:
    target: str   # "hr" | "branch:<id>" | "employee:<id>"
    kind: str
    text: str


def collect(db: Session, today: date | None = None) -> list[Notice]:
    today = today or date.today()
    out: list[Notice] = []

    # documents: warn at the configured lead time, a week before and on the day
    warn = {t["code"]: int(t.get("warn_days", 30)) for t in cfg("documents.types", [])}
    for d in people.expiring_documents(db, SYSTEM, max(warn.values() or [30]), today):
        if d["days_left"] in {warn.get(d["doc_type"], 30), 7, 0}:
            emp = db.get(Employee, d["employee_id"])
            text = f"📄 {d['full_name']}: {d['title']} expires {d['expires']} ({d['days_left']} d)"
            out += [Notice("hr", "document", text), Notice(f"branch:{emp.branch_id}", "document", text),
                    Notice(f"employee:{emp.id}", "document", f"📄 Your {d['title']} expires {d['expires']}. Please renew.")]

    # onboarding milestones 30/60/90
    for plan in onboarding.plans_in_scope(db, SYSTEM):
        p = onboarding.progress(plan, today)
        if p["day"] in (30, 60, 90):
            out.append(Notice(f"branch:{plan.employee.branch_id}", "onboarding",
                              f"🎓 {plan.employee.full_name}: day {p['day']} — time for the stage test "
                              f"(progress {p['progress_pct']:.0f}%, mentor: {plan.mentor or '—'})"))

    # payroll precheck 2 days before payday
    payday = int(cfg("payroll.payday", 10))
    if today.day == max(payday - 2, 1):
        month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        pc = payroll.precheck(db, SYSTEM, month)
        if pc["count"]:
            out.append(Notice("hr", "payroll", f"💰 Payroll {month}: {pc['count']} issue(s) before payout, "
                                               f"at risk ≈ {pc['amount_at_risk'] or 0:,} {cfg('company.currency', 'UZS')}"))

    # anonymous monthly eNPS (on the configured day) + exit survey for people who left in the last 3 days
    month = today.strftime("%Y-%m")
    asked = {(p.employee_id, p.kind) for p in db.scalars(select(PulseSent).where(PulseSent.month == month))}
    linked = list(db.scalars(select(Employee).where(Employee.telegram_id.is_not(None))))
    if cfg("engagement.enps_day") and today.day == int(cfg("engagement.enps_day")):
        for e in linked:
            if e.status != "fired" and (e.id, "enps") not in asked:
                db.add(PulseSent(employee_id=e.id, kind="enps", month=month))
                out.append(Notice(f"employee:{e.id}", "pulse_enps",
                                  "📊 Anonim so'rov: bizni do'stlaringizga ish joyi sifatida tavsiya qilasizmi? (0–10)\n"
                                  "Анонимный опрос: порекомендуете ли вы нас друзьям как место работы? (0–10)"))
    for e in linked:
        if e.status == "fired" and e.fire_date and 0 <= (today - e.fire_date).days <= 3 and (e.id, "exit") not in asked:
            db.add(PulseSent(employee_id=e.id, kind="exit", month=month))
            out.append(Notice(f"employee:{e.id}", "pulse_exit",
                              "🙏 Biz bilan ishlaganingiz uchun rahmat. Ketishingizning asosiy sababi? (anonim)\n"
                              "Спасибо за работу. Главная причина ухода? (анонимно)"))

    # unread SOPs: remind once a week (Monday)
    if today.weekday() == 0:
        from . import engagement
        for e in linked:
            if e.status != "fired":
                unread = engagement.my_unread(db, e)
                if unread:
                    out.append(Notice(f"employee:{e.id}", "sop", "📘 Yangi/yangilangan qoidalar / Новые правила: "
                                      + ", ".join(u["title"] for u in unread[:5]) + " — Suhayl'ga «o'qidim» deb yozing."))

    # requests waiting > 24h
    stale = db.scalars(select(LeaveRequest).where(LeaveRequest.status == "pending",
                                                  LeaveRequest.created_at <= today - timedelta(days=1)))
    for r in stale:
        out.append(Notice(f"branch:{r.employee.branch_id}", "request",
                          f"📝 Request #{r.id} ({r.kind}) from {r.employee.full_name} waits for a decision"))
    return out


def branch_lead_telegram_ids(db: Session, branch_id: int) -> list[int]:
    ids = db.scalars(select(Employee.telegram_id).join(BranchLead, BranchLead.employee_id == Employee.id)
                     .where(BranchLead.branch_id == branch_id, Employee.telegram_id.is_not(None)))
    return list(ids)
