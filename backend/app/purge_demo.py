"""Remove seeded demo data, keep real data: imported people (external_refs), people linked by real bot registrations,
real registrations, admin user, roles, audit log. python -m app.purge_demo --yes"""
from __future__ import annotations

import sys

from sqlalchemy import delete, or_, select

from .db import SessionLocal
from .models import (Absence, AdDeal, ApprovalRequest, AttendanceEvent, Branch, BranchLead, Candidate, Department, Document,
                     Employee, ExternalRef, HrOverride, KpiMetric, KpiValue, LeadReport, LeaveRequest, MaterialSend,
                     OnboardingItem, OnboardingPlan, PayrollEntry, PeriodStatus, Position, PulseResponse, PulseSent, Region,
                     Registration, SalesRecord, Sop, SopAck, User, Vacancy)
from .rbac import audit

DEMO_TG = {3001, 3002, 3003}


def purge() -> dict:
    with SessionLocal() as db:
        keep = set(db.scalars(select(ExternalRef.local_id).where(ExternalRef.kind == "employee")))
        keep |= {r.employee_id for r in db.scalars(select(Registration).where(Registration.telegram_id.not_in(DEMO_TG)))
                 if r.employee_id}
        demo = [e.id for e in db.scalars(select(Employee)) if e.id not in keep]
        by_emp = [AttendanceEvent, LeadReport, HrOverride, Absence, PayrollEntry, Document, SopAck, PulseSent, KpiValue,
                  MaterialSend, BranchLead]
        n = {}
        for m in by_emp:
            n[m.__tablename__] = db.execute(delete(m).where(m.employee_id.in_(demo))).rowcount
        n["leave_requests"] = db.execute(delete(LeaveRequest).where(LeaveRequest.employee_id.in_(demo))).rowcount
        n["sales_records"] = db.execute(delete(SalesRecord).where(or_(SalesRecord.employee_id.in_(demo),
                                                                        SalesRecord.source != "smartup"))).rowcount
        plans = list(db.scalars(select(OnboardingPlan.id).where(OnboardingPlan.employee_id.in_(demo))))
        db.execute(delete(OnboardingItem).where(OnboardingItem.plan_id.in_(plans)))
        n["onboarding_plans"] = db.execute(delete(OnboardingPlan).where(OnboardingPlan.id.in_(plans))).rowcount
        db.execute(delete(Registration).where(Registration.telegram_id.in_(DEMO_TG)))
        n["employees"] = db.execute(delete(Employee).where(Employee.id.in_(demo))).rowcount
        for m in (Candidate, AdDeal, Vacancy, Sop, PulseResponse, ApprovalRequest, PeriodStatus, KpiValue, KpiMetric):
            n[m.__tablename__] = db.execute(delete(m)).rowcount
        n["users"] = db.execute(delete(User).where(User.username != "admin")).rowcount
        # dictionaries nobody uses any more
        used_br = set(db.scalars(select(Employee.branch_id))) - {None}
        n["branches"] = db.execute(delete(Branch).where(Branch.id.not_in(used_br or {-1}))).rowcount
        used_rg = set(db.scalars(select(Branch.region_id))) - {None}
        n["regions"] = db.execute(delete(Region).where(Region.id.not_in(used_rg or {-1}))).rowcount
        used_pos = set(db.scalars(select(Employee.position_id))) - {None}
        n["positions"] = db.execute(delete(Position).where(Position.id.not_in(used_pos or {-1}))).rowcount
        used_dep = set(db.scalars(select(Employee.department_id))) - {None}
        n["departments"] = db.execute(delete(Department).where(Department.id.not_in(used_dep or {-1}))).rowcount
        n["kept_employees"] = len(keep)
        audit(db, None, "purge_demo", None, **{k: v for k, v in n.items()})
        db.commit()
        return n


if __name__ == "__main__":
    if "--yes" not in sys.argv:
        raise SystemExit("Deletes demo data. Run with --yes")
    print(purge())
