"""One database for panel, bots and agents — no hourly sync between copies."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now()


class Region(Base):
    __tablename__ = "regions"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))


class Branch(Base):
    __tablename__ = "branches"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"))
    city: Mapped[str | None] = mapped_column(String(80))
    mode: Mapped[str] = mapped_column(String(10), default="day")  # day | 24/7
    lat: Mapped[float | None] = mapped_column(Float)          # geofence centre for check-in
    lon: Mapped[float | None] = mapped_column(Float)
    radius_m: Mapped[int | None] = mapped_column(Integer)
    qr_secret: Mapped[str | None] = mapped_column(String(64))  # rotating check-in code shown by the head
    region: Mapped[Region | None] = relationship()


class Position(Base):
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    is_manager: Mapped[bool] = mapped_column(Boolean, default=False)


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160), index=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    telegram_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), index=True)
    position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id"))
    hire_date: Mapped[date | None] = mapped_column(Date)
    fire_date: Mapped[date | None] = mapped_column(Date)
    fire_reason: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="active")  # probation | active | fired
    pay_type: Mapped[str] = mapped_column(String(10), default="monthly")  # monthly | hourly | daily
    base_salary: Mapped[int | None] = mapped_column(Integer)  # UZS; None = unknown
    schedule_code: Mapped[str] = mapped_column(String(40), default="day_9_18")
    schedule_anchor: Mapped[date | None] = mapped_column(Date)  # per-person shift offset for cycle schedules
    leave_balance_days: Mapped[float | None] = mapped_column(Float)
    allowances: Mapped[dict] = mapped_column(JSON, default=dict)

    branch: Mapped[Branch | None] = relationship()
    position: Mapped[Position | None] = relationship()

    @property
    def is_active(self) -> bool:
        return self.status != "fired"


class BranchLead(Base):
    """Pharmacy head / regional manager -> branches they lead (team lead cabinet + bot scope)."""
    __tablename__ = "branch_leads"
    __table_args__ = (UniqueConstraint("branch_id", "employee_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))


class User(Base):
    """Web panel login (office, HR, payroll, executives, regional managers)."""
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    full_name: Mapped[str] = mapped_column(String(160), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))  # admin | hr_manager | payroll | executive | manager | recruiter
    branch_scope: Mapped[list | None] = mapped_column(JSON, default=None)  # None = all branches
    can_see_payroll: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AttendanceEvent(Base):
    __tablename__ = "attendance_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    kind: Mapped[str] = mapped_column(String(4))  # in | out
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    source: Mapped[str] = mapped_column(String(20), default="telegram")
    verified: Mapped[str | None] = mapped_column(String(10))  # geo | qr | none — how the place was proven
    distance_m: Mapped[int | None] = mapped_column(Integer)


class LeadReport(Base):
    """Team lead's 'came / absent' + hours (0.5..24) for a person and day."""
    __tablename__ = "lead_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(10))  # came | absent
    hours: Mapped[float | None] = mapped_column(Float)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)


class HrOverride(Base):
    __tablename__ = "hr_overrides"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    check_in: Mapped[datetime | None] = mapped_column(DateTime)
    check_out: Mapped[datetime | None] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(String(300))
    author: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Absence(Base):
    __tablename__ = "absences"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # vacation | sick_leave | trip | excused | unexcused
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    paid: Mapped[bool] = mapped_column(Boolean, default=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("leave_requests.id"))


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    date_from: Mapped[date | None] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)
    days: Mapped[float | None] = mapped_column(Float)
    comment: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | approved | rejected
    channel: Mapped[str] = mapped_column(String(20), default="panel")  # panel | suhayl | miniapp
    decided_by: Mapped[str | None] = mapped_column(String(80))
    decision_reason: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    employee: Mapped[Employee] = relationship()


class ApprovalRequest(Base):
    """An agent asked for one of the human-only actions. A person decides."""
    __tablename__ = "approval_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(40))
    summary: Mapped[str] = mapped_column(String(400))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))
    requested_by: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(10), default="pending")
    decided_by: Mapped[str | None] = mapped_column(String(80))
    decision_reason: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)


class PayrollEntry(Base):
    __tablename__ = "payroll_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    month: Mapped[str] = mapped_column(String(7), index=True)  # YYYY-MM
    kind: Mapped[str] = mapped_column(String(20))  # advance | bonus | penalty | other | warning | kpi
    amount: Mapped[int] = mapped_column(Integer, default=0)  # for kpi: score 0..120
    reason: Mapped[str] = mapped_column(String(300))
    author: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    cancel_reason: Mapped[str | None] = mapped_column(String(300))


class PeriodStatus(Base):
    """Tabel close + payroll status per month."""
    __tablename__ = "period_status"
    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    tabel_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    payroll_status: Mapped[str] = mapped_column(String(12), default="draft")  # draft|calculated|approved|paid|closed
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime)
    changed_after_calc: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(String(80))
    approve_reason: Mapped[str | None] = mapped_column(String(300))


class SalesRecord(Base):
    __tablename__ = "sales_records"
    __table_args__ = (UniqueConstraint("employee_id", "month"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    month: Mapped[str] = mapped_column(String(7))
    amount: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(20), default="csv")


class OnboardingPlan(Base):
    __tablename__ = "onboarding_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), unique=True)
    mentor: Mapped[str | None] = mapped_column(String(160))
    start_date: Mapped[date] = mapped_column(Date)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)  # {"30": 72}
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    employee: Mapped[Employee] = relationship()
    items: Mapped[list["OnboardingItem"]] = relationship(cascade="all, delete-orphan", order_by="OnboardingItem.id")


class OnboardingItem(Base):
    __tablename__ = "onboarding_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("onboarding_plans.id"))
    stage: Mapped[int] = mapped_column(Integer)  # 30 | 60 | 90
    title: Mapped[str] = mapped_column(String(200))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    done_at: Mapped[datetime | None] = mapped_column(DateTime)
    done_by: Mapped[str | None] = mapped_column(String(80))


class Sop(Base):
    """Single SOP / knowledge library for every agent and the panel."""
    __tablename__ = "sops"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    position_code: Mapped[str | None] = mapped_column(String(40))
    body: Mapped[str] = mapped_column(Text)
    tags: Mapped[str] = mapped_column(String(300), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class SopAck(Base):
    """'I have read it' for a specific SOP version (updated_at at the moment of reading)."""
    __tablename__ = "sop_acks"
    __table_args__ = (UniqueConstraint("sop_id", "employee_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    sop_id: Mapped[int] = mapped_column(ForeignKey("sops.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    version: Mapped[str] = mapped_column(String(32))
    ack_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class PulseResponse(Base):
    """Anonymous by design: no employee id is stored — only branch, month and kind."""
    __tablename__ = "pulse_responses"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # enps | exit
    month: Mapped[str] = mapped_column(String(7), index=True)
    branch_id: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[int] = mapped_column(Integer)  # 0..10
    reason: Mapped[str | None] = mapped_column(String(40))  # exit: pay | schedule | manager | workload | growth | personal | other
    comment: Mapped[str | None] = mapped_column(String(500))


class PulseSent(Base):
    """Who was asked / answered (to avoid double votes) — kept apart from the answers."""
    __tablename__ = "pulse_sent"
    __table_args__ = (UniqueConstraint("employee_id", "kind", "month"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    kind: Mapped[str] = mapped_column(String(10))
    month: Mapped[str] = mapped_column(String(7))
    answered: Mapped[bool] = mapped_column(Boolean, default=False)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(40))
    number: Mapped[str | None] = mapped_column(String(80))
    issued: Mapped[date | None] = mapped_column(Date)
    expires: Mapped[date | None] = mapped_column(Date)
    employee: Mapped[Employee] = relationship()


class Vacancy(Base):
    __tablename__ = "vacancies"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    position_code: Mapped[str | None] = mapped_column(String(40))
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))
    salary_text: Mapped[str | None] = mapped_column(String(200))
    schedule_text: Mapped[str | None] = mapped_column(String(200))
    requirements: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(10), default="draft")  # draft | open | closed
    opened_at: Mapped[date | None] = mapped_column(Date)
    closed_at: Mapped[date | None] = mapped_column(Date)
    sla_days: Mapped[int] = mapped_column(Integer, default=21)
    ad_text: Mapped[str | None] = mapped_column(Text)
    branch: Mapped[Branch | None] = relationship()


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    vacancy_id: Mapped[int | None] = mapped_column(ForeignKey("vacancies.id"))
    full_name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(32))
    telegram_id: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(20), default="bot")
    answers: Mapped[list] = mapped_column(JSON, default=list)
    score: Mapped[int | None] = mapped_column(Integer)
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    label: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), default="new")  # new | shortlist | hired | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime)  # personal-data consent given in the bot
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)  # for the retention purge
    vacancy: Mapped[Vacancy | None] = relationship()


class AdDeal(Base):
    __tablename__ = "ad_deals"
    id: Mapped[int] = mapped_column(primary_key=True)
    vacancy_id: Mapped[int | None] = mapped_column(ForeignKey("vacancies.id"))
    channel: Mapped[str] = mapped_column(String(120))
    subscribers: Mapped[int | None] = mapped_column(Integer)
    admin_contact: Mapped[str | None] = mapped_column(String(120))
    stage: Mapped[str] = mapped_column(String(16), default="found")
    # found|contacted|negotiating|agreed|to_pay|paid|scheduled|human|declined
    budget: Mapped[int | None] = mapped_column(Integer)
    price: Mapped[int | None] = mapped_column(Integer)
    post_at: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent: Mapped[str] = mapped_column(String(20), index=True)
    user_key: Mapped[str] = mapped_column(String(60), index=True)
    branch_id: Mapped[int | None] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(10))  # user | assistant
    text: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    actor: Mapped[str] = mapped_column(String(80))
    actor_role: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(60))
    target: Mapped[str | None] = mapped_column(String(120))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
