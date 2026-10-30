"""Roles + branch scope. Every service query takes a Scope, so a pharmacy head
can never read another pharmacy — enforced in code, not in a prompt."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import AuditLog, BranchLead, Employee, Role, User

# Bot roles (Telegram side)
BOT_ROLES = ["guest", "employee", "manager", "hr_head", "owner"]

# Every permission a role can hold, with what it lets a person do (shown in the role builder). "*" = main admin.
PERMISSIONS: dict[str, dict[str, str]] = {
    "hr.read": {"uz": "Xodimlar, davomat, tabel, so'rovlarni ko'rish", "ru": "Просмотр сотрудников, посещаемости, табеля, заявок"},
    "hr.write": {"uz": "Xodim, lavozim, hudud, filial qo'shish va tahrirlash", "ru": "Добавление и правка сотрудников, должностей, регионов, филиалов"},
    "attendance.write": {"uz": "Tabelni tuzatish, oyni yopish/ochish", "ru": "Правка табеля, закрытие/открытие месяца"},
    "requests.decide": {"uz": "Ta'til va boshqa so'rovlarni tasdiqlash", "ru": "Решения по отпускам и заявкам"},
    "registrations": {"uz": "Botdan kelgan xodim arizalarini qabul qilish, bot funksiyalarini ochish", "ru": "Приём заявок сотрудников из бота, выдача функций бота"},
    "recruiting.read": {"uz": "Vakansiya va nomzodlarni ko'rish", "ru": "Просмотр вакансий и кандидатов"},
    "recruiting": {"uz": "Vakansiya ochish, nomzodlar bilan ishlash", "ru": "Открытие вакансий, работа с кандидатами"},
    "hh.search": {"uz": "HeadHunter (hh.uz) bazasidan nomzod qidirish", "ru": "Поиск кандидатов в базе HeadHunter (hh.uz)"},
    "onboarding": {"uz": "Onboarding rejalari, material va suhbat yuborish", "ru": "Онбординг: планы, материалы, беседы"},
    "broadcast": {"uz": "Xodimlarga bot orqali xabar yuborish", "ru": "Рассылка сотрудникам через бота"},
    "documents": {"uz": "Xodim hujjatlarini yuritish", "ru": "Ведение документов сотрудников"},
    "payroll.read": {"uz": "Oylik, KPI, bonuslarni ko'rish", "ru": "Просмотр зарплат, KPI, бонусов"},
    "payroll.write": {"uz": "Avans, bonus, jarima, KPI kiritish", "ru": "Ввод авансов, бонусов, штрафов, KPI"},
    "payroll.approve": {"uz": "Oylikni tasdiqlash va to'langan deb belgilash", "ru": "Утверждение и выплата зарплаты"},
    "analytics": {"uz": "HR tahlil: KPI, ABC, 80/20, hisobotlar", "ru": "HR-аналитика: KPI, ABC, 80/20, отчёты"},
    "audit.read": {"uz": "Audit jurnalini ko'rish", "ru": "Просмотр журнала аудита"},
}

# Built-in roles (seeded into the roles table; the main admin edits them or builds new ones).
PANEL_PERMS: dict[str, set[str]] = {
    "admin": {"*"},
    "ceo": {"*"},
    "hr_manager": {"hr.read", "hr.write", "attendance.write", "requests.decide", "registrations", "recruiting", "onboarding",
                   "broadcast", "documents", "analytics"},
    "payroll": {"hr.read", "payroll.read", "payroll.write", "payroll.approve", "analytics"},
    "executive": {"hr.read", "payroll.read", "recruiting.read", "analytics", "audit.read"},
    "manager": {"hr.read"},
    "recruiter": {"recruiting", "hh.search"},
}
ROLE_NAMES = {"admin": "Bosh admin / Главный админ", "ceo": "CEO", "hr_manager": "HR menejer / HR-менеджер",
              "payroll": "Hisob-kitob / Расчёт ЗП", "executive": "Rahbariyat / Руководство", "manager": "Filial rahbari / Руководитель",
              "recruiter": "Rekruter / Рекрутер"}

# Bot functions (sub-agents) HR opens per employee. Agent -> function key.
BOT_FUNCTIONS: dict[str, dict[str, str]] = {
    "helpdesk": {"uz": "So'rovlar, jadval, qoidalar (Suhayl)", "ru": "Заявки, график, правила (Сухайл)"},
    "attendance": {"uz": "Davomat va hisobotlar (Hamza)", "ru": "Посещаемость и отчёты (Хамза)"},
    "onboarding": {"uz": "Onboarding 30/60/90 (Ozoda)", "ru": "Онбординг 30/60/90 (Озода)"},
    "payroll": {"uz": "Oylik tekshiruvi (Bexruz)", "ru": "Проверка ЗП (Бехруз)"},
    "analytics": {"uz": "HR tahlil (Husayn)", "ru": "HR-аналитика (Хусайн)"},
    "recruiting": {"uz": "Rekruting (Rauf)", "ru": "Рекрутинг (Рауф)"},
}
AGENT_FUNCTION = {"hr": "attendance", "suhayl": "helpdesk", "hamza": "attendance", "ozoda": "onboarding", "bexruz": "payroll",
                  "husayn": "analytics", "rauf": "recruiting", "reklama": "recruiting"}

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
    functions: set[str] | None = None  # bot functions; None = all (owner / HR)
    hidden: set[str] = field(default_factory=set)  # data categories hidden in this chat (services/visibility.py)

    def has_function(self, agent: str) -> bool:
        return self.functions is None or AGENT_FUNCTION.get(agent, agent) in self.functions

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
    fn = set(emp.bot_functions or [])
    if is_manager_position(emp):
        branches = led_branches(db, emp.id) or ({emp.branch_id} if emp.branch_id else set())
        return Scope(actor, "manager", branches, False, emp.id, functions=fn)
    return Scope(actor, "employee", {emp.branch_id} if emp.branch_id else set(), False, emp.id, functions=fn)


def role_perms(db: Session | None, code: str) -> set[str]:
    """Roles table first (built in the panel), built-in defaults as fallback."""
    if db is not None:
        r = db.scalar(select(Role).where(Role.code == code))
        if r is not None:
            return {p for p in r.perms if p == "*" or p in PERMISSIONS}
    return set(PANEL_PERMS.get(code, set()))


def scope_for_user(user: User, db: Session | None = None) -> Scope:
    perms = role_perms(db, user.role)
    full = "*" in perms
    payroll = full or user.can_see_payroll
    branches = None if full or user.branch_scope is None else set(user.branch_scope)
    return Scope(f"user:{user.username}", user.role, branches, payroll, None, perms)


def seed_roles(db: Session) -> None:
    for code, perms in PANEL_PERMS.items():
        if not db.scalar(select(Role).where(Role.code == code)):
            db.add(Role(code=code, name=ROLE_NAMES.get(code, code), perms=sorted(perms), system=True))
    db.flush()


def audit(db: Session, scope: Scope | None, action: str, target: str | None = None, **details) -> None:
    db.add(AuditLog(actor=scope.actor if scope else "system", actor_role=scope.role if scope else "system",
                    action=action, target=target, details=details))
