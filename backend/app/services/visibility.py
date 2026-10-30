"""Who sees what in the bot — separately in the HR group and in private chat. Set in the panel by the main admin.
Per bot role (owner / hr_head / manager / employee) with per-person overrides by Telegram id. Default: everything allowed.
Hiding a category removes its agent tools for that chat; hiding 'payroll' also hides salaries on employee cards."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Employee, Setting

KEY = "bot_visibility"
CHANNELS = ("group", "private")
ROLES = ("owner", "hr_head", "manager", "employee")
CATEGORIES: dict[str, dict[str, str]] = {
    "payroll": {"uz": "Oylik, jarima, bonus summalari", "ru": "Зарплаты, штрафы, бонусы (суммы)"},
    "attendance": {"uz": "Davomat, kechikish, tabel", "ru": "Посещаемость, опоздания, табель"},
    "people": {"uz": "Xodimlar kartasi, telefonlar, hujjatlar", "ru": "Карточки сотрудников, телефоны, документы"},
    "recruiting": {"uz": "Vakansiya, nomzod, hh.uz, ish taklifi", "ru": "Вакансии, кандидаты, hh.uz, офферы"},
    "onboarding": {"uz": "Onboarding, materiallar, yangi xodimlar", "ru": "Онбординг, материалы, новички"},
    "analytics": {"uz": "Tahlil, savdo reytingi, eNPS, xavf", "ru": "Аналитика, рейтинг продаж, eNPS, риски"},
}
TOOL_CATEGORY = {
    **{t: "payroll" for t in ("payroll_summary", "payroll_precheck")},
    **{t: "attendance" for t in ("hr_overview", "attendance_day", "attendance_rate", "overtime", "discipline_ranking",
                                 "employee_month", "attendance_by_department")},
    **{t: "people" for t in ("search_employee", "employee_card", "headcount", "turnover", "documents_expiring",
                             "hr_document", "new_hires")},
    **{t: "recruiting" for t in ("vacancies_sla", "vacancies_list", "candidates", "vacancy_draft", "vacancy_write",
                                 "vacancy_publish", "ads_deals", "ads_add_channel", "interview_invite", "hh_search",
                                 "interview_slots", "interview_slots_add", "job_offer")},
    **{t: "onboarding" for t in ("onboarding_status", "onboarding_plan", "onboarding_add", "onboarding_score",
                                 "onboarding_mark_item", "onboarding_course_plan", "onboarding_course_start",
                                 "onboarding_today")},
    **{t: "analytics" for t in ("risk_signals", "pulse_summary", "sales_ranking")},
}  # tools not listed (the person's own data, rules, request_human_action) are always available


def _all() -> list[str]:
    return list(CATEGORIES)


def get(db: Session) -> dict:
    s = db.get(Setting, KEY)
    v = dict(s.value) if s else {}
    roles = v.get("roles") or {}
    return {"roles": {r: {c: list(roles.get(r, {}).get(c, _all())) for c in CHANNELS} for r in ROLES},
            "people": v.get("people") or {}, "group_report_names": v.get("group_report_names", True)}


def save(db: Session, data: dict) -> dict:
    ok = set(CATEGORIES)
    clean = lambda xs: sorted({x for x in (xs or []) if x in ok})  # noqa: E731
    roles = {r: {c: clean(data.get("roles", {}).get(r, {}).get(c, _all())) for c in CHANNELS} for r in ROLES}
    people = {}
    for tg, p in (data.get("people") or {}).items():
        if str(tg).lstrip("-").isdigit() and isinstance(p, dict):
            people[str(int(tg))] = {"name": str(p.get("name", ""))[:120], **{c: clean(p.get(c)) for c in CHANNELS}}
    v = {"roles": roles, "people": people, "group_report_names": bool(data.get("group_report_names", True))}
    s = db.get(Setting, KEY) or Setting(key=KEY, value={})
    s.value = v
    db.merge(s)
    return v


def allowed(db: Session, role: str, tg_id: int, channel: str) -> set[str]:
    v = get(db)
    p = v["people"].get(str(tg_id))
    if p is not None:
        return set(p.get(channel, _all()))
    return set(v["roles"].get(role, {}).get(channel, _all()))


def apply(db: Session, scope, tg_id: int, channel: str):
    """Hide the categories this person may not see in this chat (mutates and returns the scope)."""
    hidden = set(CATEGORIES) - allowed(db, scope.role, tg_id, channel)
    scope.hidden = hidden
    if "payroll" in hidden:
        scope.payroll = False
    return scope


def people_with_bot_access(db: Session) -> list[dict]:
    """Who can talk to the HR agent: owners, HR heads (from config) and managers linked in Telegram."""
    s = settings()
    names = {e.telegram_id: e.full_name for e in db.scalars(select(Employee).where(Employee.telegram_id.is_not(None)))}
    out = [{"tg_id": i, "name": names.get(i, ""), "role": "owner"} for i in sorted(s.owner_ids)]
    out += [{"tg_id": i, "name": names.get(i, ""), "role": "hr_head"} for i in sorted(s.hr_head_ids - s.owner_ids)]
    from ..rbac import is_manager_position
    for e in db.scalars(select(Employee).where(Employee.telegram_id.is_not(None), Employee.status != "fired")):
        if e.telegram_id not in s.owner_ids | s.hr_head_ids and is_manager_position(e):
            out.append({"tg_id": e.telegram_id, "name": e.full_name, "role": "manager"})
    return out
