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


class Department(Base):
    """Created only by the main admin."""
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Role(Base):
    """Panel role built by the main admin: a named set of permissions. `system` roles cannot be deleted."""
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500), default="")
    perms: Mapped[list] = mapped_column(JSON, default=list)
    system: Mapped[bool] = mapped_column(Boolean, default=False)


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160), index=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    telegram_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), index=True)
    bot_functions: Mapped[list] = mapped_column(JSON, default=list)  # sub-agent functions HR opened in the bot
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
    department: Mapped[Department | None] = relationship()
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
    role: Mapped[str] = mapped_column(String(40))  # roles.code (admin | ceo | hr_manager | payroll | ... | custom)
    telegram_id: Mapped[int | None] = mapped_column(Integer)      # set when the user joined through a Telegram invite
    last_login: Mapped[datetime | None] = mapped_column(DateTime)
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


class KpiMetric(Base):
    """A KPI the company measures. Applies to a position and/or department (None = everyone)."""
    __tablename__ = "kpi_metrics"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(20), default="")
    direction: Mapped[str] = mapped_column(String(4), default="up")  # up = more is better | down = less is better
    target: Mapped[float] = mapped_column(Float)
    weight: Mapped[int] = mapped_column(Integer, default=1)
    position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class KpiValue(Base):
    __tablename__ = "kpi_values"
    __table_args__ = (UniqueConstraint("employee_id", "metric_id", "month"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    metric_id: Mapped[int] = mapped_column(ForeignKey("kpi_metrics.id"))
    month: Mapped[str] = mapped_column(String(7), index=True)
    value: Mapped[float] = mapped_column(Float)
    author: Mapped[str] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class ExternalRef(Base):
    """Link between our record and an id in an outside system (smartup agent, timepay employee, ...)."""
    __tablename__ = "external_refs"
    __table_args__ = (UniqueConstraint("source", "kind", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(20))  # employee | branch
    external_id: Mapped[str] = mapped_column(String(200))
    local_id: Mapped[int] = mapped_column(Integer)


class Setting(Base):
    """Small key -> JSON settings edited in the panel (analytics thresholds etc.)."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class ReportFile(Base):
    """Reports attached in HR analytics (xlsx / pdf / csv / docx)."""
    __tablename__ = "report_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    month: Mapped[str | None] = mapped_column(String(7))
    kind: Mapped[str] = mapped_column(String(20), default="other")  # kpi | abc | payroll | other
    filename: Mapped[str] = mapped_column(String(200))
    path: Mapped[str] = mapped_column(String(300))
    size: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


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


class OnboardingMaterial(Base):
    """Video / method / document HR sends to chosen employees through the bot."""
    __tablename__ = "onboarding_materials"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(10))  # video | document | link
    filename: Mapped[str | None] = mapped_column(String(200))
    path: Mapped[str | None] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(String(500))
    size: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    # who it is for (empty = everyone) and when in the first weeks it is sent
    position_ids: Mapped[list | None] = mapped_column(JSON)
    department_ids: Mapped[list | None] = mapped_column(JSON)
    day_offset: Mapped[int] = mapped_column(Integer, default=0)   # day N after the start of onboarding
    for_new: Mapped[bool] = mapped_column(Boolean, default=True)  # part of the automatic course for newcomers


class MaterialSend(Base):
    """Who got a material, and with whom a talk on it was scheduled."""
    __tablename__ = "material_sends"
    __table_args__ = (UniqueConstraint("material_id", "employee_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("onboarding_materials.id"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    talk_at: Mapped[datetime | None] = mapped_column(DateTime)
    talk_with: Mapped[str | None] = mapped_column(String(160))
    talk_done: Mapped[bool] = mapped_column(Boolean, default=False)
    talk_note: Mapped[str | None] = mapped_column(String(500))
    scheduled_for: Mapped[date | None] = mapped_column(Date)       # course item: delivered on this day
    queued: Mapped[bool] = mapped_column(Boolean, default=True)     # already handed to the bot outbox
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime)    # employee pressed "Ko'rdim"
    reason: Mapped[str | None] = mapped_column(String(300))        # why the agent picked it
    employee: Mapped[Employee] = relationship()


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
    intro: Mapped[str | None] = mapped_column(Text)        # free-text opening written by the agent
    duties: Mapped[str | None] = mapped_column(Text)       # one per line
    benefits: Mapped[str | None] = mapped_column(Text)     # one per line
    public: Mapped[bool] = mapped_column(Boolean, default=False)       # shown on the public /jobs page
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)  # kept in the library for reuse
    published: Mapped[dict | None] = mapped_column(JSON)   # platform -> when / message id (never twice)
    ad_custom: Mapped[bool] = mapped_column(Boolean, default=False)  # ad_text is a chosen variant / HR edit, not the template
    created_by: Mapped[str | None] = mapped_column(String(80))
    branch: Mapped[Branch | None] = relationship()


class VacancyRevision(Base):
    """Last versions of a vacancy text (edit / rewrite / revert)."""
    __tablename__ = "vacancy_revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    vacancy_id: Mapped[int] = mapped_column(ForeignKey("vacancies.id"), index=True)
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    ad_text: Mapped[str] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(String(500))
    author: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


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


class InterviewSlot(Base):
    """A free interview time HR offers; the candidate picks one in the bot by number."""
    __tablename__ = "interview_slots"
    id: Mapped[int] = mapped_column(primary_key=True)
    vacancy_id: Mapped[int | None] = mapped_column(ForeignKey("vacancies.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    minutes: Mapped[int] = mapped_column(Integer, default=30)
    place: Mapped[str] = mapped_column(String(300), default="")       # address or meeting link
    interviewer: Mapped[str] = mapped_column(String(160), default="")
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidates.id"))
    status: Mapped[str] = mapped_column(String(10), default="free")   # free | booked | done | cancelled
    reminded: Mapped[bool] = mapped_column(Boolean, default=False)    # legacy (v0.3 single reminder)
    reminded_day: Mapped[bool] = mapped_column(Boolean, default=False)   # day before, at recruiting.interviews.remind_day_before_at
    reminded_hour: Mapped[bool] = mapped_column(Boolean, default=False)  # N minutes before
    booked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[str] = mapped_column(String(80), default="")


class CandidateStep(Base):
    """Open step waiting for the candidate's answer in the bot: slot choice or offer."""
    __tablename__ = "candidate_steps"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))                     # slots | offer
    data: Mapped[dict] = mapped_column(JSON, default=dict)            # slots: {"ids": [...]}; offer: position, salary, start, text
    status: Mapped[str] = mapped_column(String(10), default="open")   # open | done | declined | cancelled
    created_by: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime)
    candidate: Mapped["Candidate"] = relationship()


class DocTemplate(Base):
    """HR document template: plain text with {placeholders}; HR edits it in the panel."""
    __tablename__ = "doc_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[str] = mapped_column(String(80), default="")


class HrDoc(Base):
    """An issued document: the rendered text is kept, the PDF is rebuilt on download."""
    __tablename__ = "hr_docs"
    id: Mapped[int] = mapped_column(primary_key=True)
    template_code: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    number: Mapped[str] = mapped_column(String(40))
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    missing: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    employee: Mapped["Employee | None"] = relationship()


class Nudge(Base):
    """Weekly discipline reminder drafted by the system; goes out only after HR approves (and may edit) it."""
    __tablename__ = "nudges"
    __table_args__ = (UniqueConstraint("employee_id", "week"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    week: Mapped[str] = mapped_column(String(10))                      # monday ISO date
    late_days: Mapped[int] = mapped_column(Integer, default=0)
    late_min: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="draft")   # draft | sent | skipped
    decided_by: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    employee: Mapped["Employee"] = relationship()


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


class Registration(Base):
    """'I am an employee' request from the bot. HR links it to a card and opens bot functions."""
    __tablename__ = "registrations"
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, index=True)
    tg_username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str] = mapped_column(String(160))
    position_text: Mapped[str] = mapped_column(String(160))
    region_text: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | approved | rejected
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    functions: Mapped[list] = mapped_column(JSON, default=list)
    decided_by: Mapped[str | None] = mapped_column(String(80))
    decision_reason: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    # access requests: a stranger wrote to an agent bot -> silent, recorded here for HR
    source: Mapped[str] = mapped_column(String(10), default="form")  # form ("I am an employee") | access (stranger)
    bots: Mapped[list | None] = mapped_column(JSON)
    last_at: Mapped[datetime | None] = mapped_column(DateTime)
    requests: Mapped[int] = mapped_column(Integer, default=1)


class PanelInvite(Base):
    """'Add via Telegram': a one-time link to the bot; the person opens it, HR approves, the bot sends a login."""
    __tablename__ = "panel_invites"
    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(40), unique=True)
    role: Mapped[str] = mapped_column(String(40))
    branch_scope: Mapped[list | None] = mapped_column(JSON)
    can_see_payroll: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | pending | approved | rejected | expired
    telegram_id: Mapped[int | None] = mapped_column(Integer)
    tg_name: Mapped[str | None] = mapped_column(String(160))
    tg_username: Mapped[str | None] = mapped_column(String(64))
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Outbox(Base):
    """Messages the panel wants the bot to send (the API process has no bot). The bot polls and marks sent."""
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(String(300))  # attachment stored under data/uploads
    buttons: Mapped[list | None] = mapped_column(JSON)  # [[{"text":..,"callback_data"|"url":..}]] inline keyboard
    topic: Mapped[str | None] = mapped_column(String(20))  # report kind -> forum topic when sent to the reports group
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    error: Mapped[str | None] = mapped_column(String(300))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime)  # taken by the bot: never sent a second time
    dedupe_key: Mapped[str | None] = mapped_column(String(80), index=True)  # same decision twice -> one message


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


# ---------------- AI camera (signed webhook -> attendance) ----------------

class CameraDelivery(Base):
    """One row per webhook delivery id: a retried delivery is never processed twice. Photos are stripped before saving."""
    __tablename__ = "camera_deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[str] = mapped_column(String(80), unique=True)
    event: Mapped[str] = mapped_column(String(30))
    received_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class CameraEvent(Base):
    """A person seen by the camera. Unmatched / ambiguous names are kept for HR, never guessed."""
    __tablename__ = "camera_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[str] = mapped_column(String(80), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # arrived | left
    ts: Mapped[datetime] = mapped_column(DateTime)
    day: Mapped[date] = mapped_column(Date, index=True)
    raw_name: Mapped[str] = mapped_column(String(160))
    branch_code: Mapped[str | None] = mapped_column(String(20))
    match: Mapped[str] = mapped_column(String(10))  # matched | unmatched | ambiguous
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), index=True)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)  # became / moved an attendance mark
    note: Mapped[str | None] = mapped_column(String(120))


class CameraVisit(Base):
    """Visitors per hour (counts only, no people)."""
    __tablename__ = "camera_visits"
    __table_args__ = (UniqueConstraint("day", "hour", "branch_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    hour: Mapped[int] = mapped_column(Integer)
    branch_code: Mapped[str | None] = mapped_column(String(20))
    count: Mapped[int] = mapped_column(Integer, default=0)


# ---------------- discipline rules (warnings -> fines) ----------------

class DisciplineRule(Base):
    """The rule list comes from company.yaml (seed); admins edit texts and numbers in the panel, never add or delete."""
    __tablename__ = "discipline_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(160))
    text: Mapped[str] = mapped_column(Text, default="")
    window: Mapped[str] = mapped_column(String(10), default="month")  # month | all_time | per_case
    warnings_before_fine: Mapped[int] = mapped_column(Integer, default=0)
    fine_amount: Mapped[int] = mapped_column(Integer, default=0)       # smallest currency unit
    extra_amount: Mapped[int] = mapped_column(Integer, default=0)      # tax / extra charge added to the fine
    note: Mapped[str] = mapped_column(String(300), default="")
    starts_on: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_by: Mapped[str | None] = mapped_column(String(80))


class DisciplineCase(Base):
    """One applied rule. Amounts are a snapshot: editing the rule later never changes a recorded fine."""
    __tablename__ = "discipline_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("discipline_rules.id"), index=True)
    month: Mapped[str] = mapped_column(String(7), index=True)
    outcome: Mapped[str] = mapped_column(String(10))  # warning | fine
    prior_count: Mapped[int] = mapped_column(Integer, default=0)
    fine_amount: Mapped[int] = mapped_column(Integer, default=0)
    extra_amount: Mapped[int] = mapped_column(Integer, default=0)
    entry_id: Mapped[int] = mapped_column(ForeignKey("payroll_entries.id"))
    reason: Mapped[str] = mapped_column(String(300))
    author: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    rule: Mapped[DisciplineRule] = relationship()
    employee: Mapped[Employee] = relationship()


# ---------------- vacancy studio: ad variants and tasks for the agent ----------------

class AdVariant(Base):
    """One of the 2 ad texts the agent wrote for a vacancy (checked by services/ad_check.py)."""
    __tablename__ = "ad_variants"
    id: Mapped[int] = mapped_column(primary_key=True)
    vacancy_id: Mapped[int] = mapped_column(ForeignKey("vacancies.id"), index=True)
    n: Mapped[int] = mapped_column(Integer)  # 1 | 2
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10), default="template")  # agent | template
    chosen: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AgentJob(Base):
    """A task HR gives the agent from the panel. The bot worker runs it; a person applies the result."""
    __tablename__ = "agent_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))  # vacancy_ad
    vacancy_id: Mapped[int | None] = mapped_column(ForeignKey("vacancies.id"), index=True)
    instruction: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="queued")  # queued | running | done | failed | applied
    result: Mapped[str | None] = mapped_column(Text)
    problems: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    applied_by: Mapped[str | None] = mapped_column(String(80))


class OnboardingHandoff(Base):
    """A candidate marked 'hired' in the panel / Mini App, waiting for HR to start the employee card + onboarding (one click).
    (An offer accepted in the bot creates the card itself and needs no handoff.)"""
    __tablename__ = "onboarding_handoffs"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), unique=True)
    status: Mapped[str] = mapped_column(String(10), default="waiting")  # waiting | started | dismissed
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    reason: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    decided_by: Mapped[str | None] = mapped_column(String(80))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    candidate: Mapped[Candidate] = relationship()
