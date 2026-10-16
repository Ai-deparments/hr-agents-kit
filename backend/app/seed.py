"""Load dictionaries from company.yaml and (optionally) demo data.
python -m app.seed            -> dictionaries + demo
python -m app.seed --no-demo  -> dictionaries + admin user only"""
from __future__ import annotations

import argparse
import os
import random
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_password
from .config import cfg
from .db import SessionLocal, init_db
from .models import (AttendanceEvent, Branch, BranchLead, Candidate, Document, Employee, LeadReport, LeaveRequest,
                     OnboardingPlan, PayrollEntry, Position, Region, SalesRecord, Sop, User, Vacancy)
from .services import onboarding, recruiting, schedules
from .rbac import Scope

FIRST = ["Dilnoza", "Aziza", "Jasur", "Sardor", "Malika", "Nodira", "Bekzod", "Kamola", "Otabek", "Shahnoza", "Ulugbek",
         "Gulnora", "Javlon", "Madina", "Sherzod", "Zarina", "Rustam", "Feruza", "Akmal", "Laylo", "Timur", "Sevara",
         "Farrux", "Mohira", "Islom", "Nilufar", "Doniyor", "Yulduz", "Anvar", "Barno"]
LAST = ["Karimova", "Rahimova", "Toshmatov", "Aliyev", "Yusupova", "Nazarova", "Ergashev", "Saidova", "Qodirov",
        "Mirzayeva", "Xolmatov", "Sobirova", "Normatov", "Ismoilova", "Hasanov"]


def load_dictionaries(db: Session) -> None:
    for r in cfg("regions", []):
        if not db.scalar(select(Region).where(Region.code == r["code"])):
            db.add(Region(code=r["code"], name=r["name"]))
    db.flush()
    regions = {r.code: r.id for r in db.scalars(select(Region))}
    for b in cfg("branches", []):
        if not db.scalar(select(Branch).where(Branch.code == b["code"])):
            db.add(Branch(code=b["code"], name=b["name"], region_id=regions.get(b.get("region")), city=b.get("city"),
                          mode=b.get("mode", "day")))
    for p in cfg("positions", []):
        if not db.scalar(select(Position).where(Position.code == p["code"])):
            db.add(Position(code=p["code"], title=p["title"], is_manager=bool(p.get("is_manager"))))
    db.flush()


def ensure_admin(db: Session) -> None:
    if not db.scalar(select(User).where(User.username == "admin")):
        pw = os.getenv("ADMIN_PASSWORD") or ("admin12345" if os.getenv("DEBUG") == "1" else "")
        if len(pw) < 10:
            raise SystemExit("Set ADMIN_PASSWORD (>= 10 chars) or DEBUG=1 for the demo password")
        db.add(User(username="admin", full_name="Administrator", password_hash=hash_password(pw), role="admin",
                    can_see_payroll=True))


def demo(db: Session, today: date | None = None) -> None:
    rnd = random.Random(42)
    today = today or date.today()
    if db.scalar(select(Employee.id).limit(1)):
        return
    br = {b.code: b for b in db.scalars(select(Branch))}
    pos = {p.code: p for p in db.scalars(select(Position))}
    names = iter(f"{f} {l}" for f, l in zip(FIRST * 2, LAST * 4))

    def emp(branch, position, salary, sched="day_9_18", hired_days=400, pay="monthly", anchor_shift=0, tg=None, status="active"):
        e = Employee(full_name=next(names), phone=f"+99890{rnd.randint(1000000, 9999999)}", branch_id=br[branch].id,
                     position_id=pos[position].id, hire_date=today - timedelta(days=hired_days), status=status,
                     pay_type=pay, base_salary=salary, schedule_code=sched, telegram_id=tg,
                     schedule_anchor=date(2026, 1, 1) + timedelta(days=anchor_shift), leave_balance_days=rnd.choice([6, 12, 18, 21]),
                     allowances={"transport": 200000} if rnd.random() < 0.5 else {})
        db.add(e)
        db.flush()
        return e

    staff = []
    # P01 is 24/7: pharmacists on 24/48 shifts offset so one is always on duty
    head1 = emp("P01", "head", 9_000_000, tg=1001)
    staff += [head1] + [emp("P01", "pharmacist", 6_500_000, "sutki_1_2", 300 - i * 40, "hourly" if i == 2 else "monthly", i)
                        for i in range(3)]
    staff += [emp("P01", "cashier", 4_500_000, "shift_2_2", 200, anchor_shift=0), emp("P01", "cashier", 4_500_000, "shift_2_2", 25, anchor_shift=2, status="probation")]
    head2 = emp("P02", "head", 8_500_000, "day_6x", tg=1002)
    staff += [head2] + [emp("P02", "pharmacist", 6_000_000, "day_6x", d) for d in (500, 50, 12)]
    staff += [emp("P02", "cashier", 4_200_000, "day_6x", 90), emp("P02", "cleaner", 2_800_000, "day_6x", 700, "daily")]
    head3 = emp("P03", "head", 8_000_000, "day_6x", tg=1003)
    staff += [head3] + [emp("P03", "provisor", 7_000_000, "day_6x", d) for d in (800, 40)]
    staff += [emp("P03", "cashier", None, "day_6x", 15, status="probation")]  # unknown salary -> shows as '—'
    regional = emp("OFC", "regional", 12_000_000, tg=1004)
    staff += [regional, emp("OFC", "accountant", 7_500_000, tg=1005), emp("OFC", "hr", 7_000_000, tg=1006),
              emp("OFC", "courier", 3_500_000, "day_6x", 60, tg=1007)]
    # a link for the dev Mini App user (DEV_TELEGRAM_ID=2001)
    staff[1].telegram_id = 2001
    for b, h in (("P01", head1), ("P02", head2), ("P03", head3)):
        db.add(BranchLead(branch_id=br[b].id, employee_id=h.id))
    for b in ("P01", "P02"):
        db.add(BranchLead(branch_id=br[b].id, employee_id=regional.id))
    # people who left (turnover history, incl. one who left in the first 30 days)
    for i, (b, p, hired, worked) in enumerate([("P01", "pharmacist", 200, 20), ("P02", "cashier", 150, 100), ("P03", "pharmacist", 90, 60)]):
        e = emp(b, p, 5_000_000, hired_days=hired, status="fired")
        e.fire_date, e.fire_reason = e.hire_date + timedelta(days=worked), "own wish"

    # attendance for the last 21 days
    for e in staff:
        d = today - timedelta(days=21)
        while d <= today:
            if schedules.employed_on(e, d) and schedules.is_workday(e, d):
                start = schedules.planned_start(e, d)
                roll = rnd.random()
                if roll < 0.06:
                    pass  # unmarked
                elif roll < 0.09 and d < today:
                    db.add(LeadReport(employee_id=e.id, day=d, status="absent", author_id=head1.id))
                else:
                    late = rnd.choice([0, 0, 0, 0, 5, 25, 40]) if roll < 0.5 else 0
                    t_in = start + timedelta(minutes=rnd.randint(-15, 3) + late)
                    t_out = t_in + timedelta(hours=schedules.planned_hours(e, d) + (schedules.lunch_hours(e)), minutes=rnd.randint(-10, 30))
                    if t_in <= datetime.now():
                        db.add(AttendanceEvent(employee_id=e.id, kind="in", ts=t_in))
                    if t_out <= datetime.now() and not (roll > 0.97):  # a few forgotten check-outs
                        db.add(AttendanceEvent(employee_id=e.id, kind="out", ts=t_out))
            d += timedelta(days=1)

    month = today.strftime("%Y-%m")
    db.add(PayrollEntry(employee_id=staff[1].id, month=month, kind="advance", amount=1_500_000, reason="Mid-month advance", author="seed"))
    db.add(PayrollEntry(employee_id=staff[2].id, month=month, kind="bonus", amount=2_500_000, reason="Plan overfulfilled", author="seed"))
    db.add(PayrollEntry(employee_id=staff[3].id, month=month, kind="warning", amount=0, reason="Cash desk discipline", author="seed"))
    db.add(PayrollEntry(employee_id=staff[7].id, month=month, kind="kpi", amount=95, reason="Mystery shopper 95", author="seed"))
    for e in staff[:8]:
        db.add(SalesRecord(employee_id=e.id, month=month, amount=rnd.randint(40, 160) * 1_000_000))

    db.add(LeaveRequest(employee_id=staff[2].id, kind="vacation", date_from=today + timedelta(days=10),
                        date_to=today + timedelta(days=16), days=7, comment="Family trip", channel="suhayl"))
    db.add(LeaveRequest(employee_id=staff[8].id, kind="certificate", comment="Work certificate for bank", channel="suhayl"))

    docs = [(staff[1], "certificate", 20), (staff[2], "med_book", 5), (staff[7], "certificate", 45), (staff[12], "med_check", -3)]
    for e, t, days in docs:
        db.add(Document(employee_id=e.id, doc_type=t, number=f"N{rnd.randint(1000, 9999)}", expires=today + timedelta(days=days)))

    hr = Scope("seed", "owner")
    for e in [x for x in staff if x.hire_date and (today - x.hire_date).days <= 95]:
        plan = onboarding.create_plan(db, hr, e, mentor=None if e.position.code == "cashier" else head1.full_name)
        for item in plan.items[: rnd.randint(0, len(plan.items))]:
            item.done = True
        if (today - e.hire_date).days > 28:
            plan.scores = {"30": rnd.choice([55, 72, 88])}

    sops = [
        ("Cold chain storage", "pharmacist", "Keep vaccines and insulin at +2..+8 °C. Log the fridge temperature twice per shift. "
         "If out of range: move stock to the backup fridge and tell the head immediately."),
        ("Prescription dispensing", "pharmacist", "Prescription-only drugs are dispensed only with a valid prescription. "
         "Check the date, stamp and dosage. Record the sale in the journal."),
        ("Cash desk discipline", "cashier", "Count the cash at shift start and end with the head. Every refund needs a receipt and the head's signature."),
        ("Customer service standard", None, "Greet within 5 seconds, ask about the need, offer an analog only with a clear explanation of the difference."),
        ("Shift handover", None, "On a 24h shift, handover is at 08:00: open orders, fridge log, cash count, defects."),
    ]
    for t, p, body in sops:
        db.add(Sop(title=t, position_code=p, body=body, tags="sop"))

    v1 = Vacancy(title="Pharmacist", position_code="pharmacist", branch_id=br["P01"].id, salary_text="from 6 500 000 UZS + % of sales",
                 schedule_text="24/48 (sutki)", requirements="Pharmacy college or university diploma, valid certificate.")
    v2 = Vacancy(title="Cashier", position_code="cashier", branch_id=br["P03"].id, salary_text="4 200 000 UZS", schedule_text="6/1, 09:00-18:00")
    db.add_all([v1, v2])
    db.flush()
    for v in (v1, v2):
        recruiting.open_vacancy(db, hr, v)
    v1.opened_at = today - timedelta(days=18)
    c1 = Candidate(vacancy_id=v1.id, full_name="Sarvinoz Qosimova", phone="+998901112233", source="bot",
                   answers=[{"q": "Your pharmacy experience?", "a": "3 years in a 24/7 pharmacy, night shifts"}])
    recruiting.apply_score(db, c1, {"role_fit": {"score": 85, "comment": "3y pharmacy, certificate valid"},
                                    "specifics": {"score": 80, "comment": "named analogs correctly"},
                                    "communication": {"score": 75, "comment": "clear"},
                                    "motivation": {"score": 70, "comment": "lives nearby"}})
    c2 = Candidate(vacancy_id=v1.id, full_name="Bobur Rasulov", source="hh")
    db.add_all([c1, c2])

    pw = os.getenv("DEMO_PASSWORD", "demo12345")
    for u, role, scope_codes, pay in [("hr", "hr_manager", None, False), ("buh", "payroll", None, True),
                                      ("ceo", "executive", None, True), ("regional", "manager", ["P01", "P02"], False),
                                      ("recruiter", "recruiter", None, False)]:
        db.add(User(username=u, full_name=u.title(), password_hash=hash_password(pw), role=role,
                    branch_scope=[br[c].id for c in scope_codes] if scope_codes else None, can_see_payroll=pay))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-demo", action="store_true")
    args = ap.parse_args()
    init_db()
    with SessionLocal() as db:
        load_dictionaries(db)
        ensure_admin(db)
        if not args.no_demo:
            demo(db)
        db.commit()
    print("seed ok")


if __name__ == "__main__":
    main()
