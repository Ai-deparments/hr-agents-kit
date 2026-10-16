"""Roles + branch scope. Every service query takes a Scope, so a pharmacy head
can never read another pharmacy — enforced in code, not in a prompt."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import AuditLog, BranchLead, Employee, User

# Bot roles (Telegram side)
BOT_ROLES = ["guest", "employee", "manager", "hr_head", "owner"]

# Panel role -> permissions
PANEL_PERMS: dict[str, set[str]] = {
    "admin": {"*"},
    "hr_manager": {"hr.read", "hr.write", "attendance.write", "requests.decide", "recruiting", "onboarding", "documents"},
    "payroll": {"hr.read", "payroll.read", "payroll.write", "payroll.approve"},
    "executive": {"hr.read", "payroll.read", "recruiting.read", "audit.read"},
    "manager": {"hr.read"},
    "recruiter": {"recruiting"},
}

MANAGER_WORDS = ("head", "manager", "director", "mudir", "boshlig", "rahbar", "menejer",
                 "начальник", "руководител", "заведу", "менеджер", "директор")


def bot_role_rank(role: str) -> int:
    return BOT_ROLES.index(role) if role in BOT_ROLES else 0


@dataclass
class Scope:
    actor: str
    role: str                         # bot role or panel role
    branch_ids: set[int] | None = None  # None = all branches
    payroll: bool = False
    employee_id: int | None = None    # self (for employee-level tools)
    perms: set[str] = field(default_factory=set)

    @property
    def all_branches(self) -> bool:
        return self.branch_ids is None

    def allows_branch(self, branch_id: int | None) -> bool:
        return self.branch_ids is None or branch_id in self.branch_ids

    def can(self, perm: str) -> bool:
        if "*" in self.perms or perm in self.perms:
            return True
        # "recruiting" implies "recruiting.read"
        return perm.endswith(".read") and perm.removesuffix(".read") in self.perms

    def at_least(self, bot_role: str) -> bool:
        return bot_role_rank(self.role) >= bot_role_rank(bot_role)


def is_manager_position(emp: Employee | None) -> bool:
    if not emp or not emp.position:
        return False
    if emp.position.is_manager:
        return True
    t = emp.position.title.lower()
    return any(w in t for w in MANAGER_WORDS)


def led_branches(db: Session, employee_id: int) -> set[int]:
    return set(db.scalars(select(BranchLead.branch_id).where(BranchLead.employee_id == employee_id)))


def scope_for_telegram(db: Session, telegram_id: int) -> Scope:
    s = settings()
    emp = db.scalar(select(Employee).where(Employee.telegram_id == telegram_id))
    actor = f"tg:{telegram_id}"
    payroll_ok = telegram_id not in s.payroll_restricted_ids
    if telegram_id in s.owner_ids:
        return Scope(actor, "owner", None, payroll_ok, emp.id if emp else None)
    if telegram_id in s.hr_head_ids:
        return Scope(actor, "hr_head", None, payroll_ok, emp.id if emp else None)
    if not emp or not emp.is_active:
        return Scope(actor, "guest", set(), False, None)
    if is_manager_position(emp):
        branches = led_branches(db, emp.id) or ({emp.branch_id} if emp.branch_id else set())
        return Scope(actor, "manager", branches, False, emp.id)
    return Scope(actor, "employee", {emp.branch_id} if emp.branch_id else set(), False, emp.id)


def scope_for_user(user: User) -> Scope:
    perms = PANEL_PERMS.get(user.role, set())
    payroll = user.role == "admin" or user.can_see_payroll
    branches = None if user.role == "admin" or user.branch_scope is None else set(user.branch_scope)
    return Scope(f"user:{user.username}", user.role, branches, payroll, None, perms)


def audit(db: Session, scope: Scope | None, action: str, target: str | None = None, **details) -> None:
    db.add(AuditLog(actor=scope.actor if scope else "system", actor_role=scope.role if scope else "system",
                    action=action, target=target, details=details))
