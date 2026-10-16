"""Agent = persona + tool list + minimum role + offline commands. Add a new agent here, nothing else."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentDef:
    name: str
    title: str
    min_role: str
    tools: list[str]
    commands: dict[str, tuple[str, dict]] = field(default_factory=dict)  # /cmd -> (tool, args)
    keywords: tuple[str, ...] = ()  # for hub-bot routing


AGENTS: dict[str, AgentDef] = {a.name: a for a in [
    AgentDef("hamza", "Head of HR & attendance", "manager",
             ["hr_overview", "attendance_day", "attendance_rate", "search_employee", "employee_card", "headcount",
              "turnover", "vacancies_sla", "documents_expiring", "risk_signals", "pulse_summary", "ask_agent", "request_human_action"],
             {"/hisobot": ("attendance_day", {}), "/davomat": ("attendance_day", {}), "/overview": ("hr_overview", {})},
             ("hisobot", "report", "отчёт", "отчет", "davomat", "посещаем", "сводк")),
    AgentDef("ozoda", "Onboarding 30/60/90", "manager",
             ["search_employee", "onboarding_status", "onboarding_plan", "onboarding_add", "onboarding_score",
              "onboarding_mark_item", "find_sop", "request_human_action"],
             {"/onboarding": ("onboarding_status", {}), "/sop": ("find_sop", {})},
             ("onboarding", "adapt", "адаптац", "новичок", "наставник", "mentor", "test", "тест", "sop")),
    AgentDef("bexruz", "Payroll pre-check", "manager",
             ["attendance_day", "attendance_rate", "overtime", "payroll_precheck", "search_employee", "request_human_action"],
             {"/payrollcheck": ("payroll_precheck", {}), "/overtime": ("overtime", {}), "/attendance": ("attendance_rate", {"days": 7}),
              "/absent": ("attendance_day", {})},
             ("oylik", "зарплат", "payroll", "salary", "аванс", "штраф", "переработ", "overtime")),
    AgentDef("husayn", "HR analytics", "manager",
             ["headcount", "turnover", "attendance_day", "attendance_rate", "vacancies_sla", "onboarding_status",
              "documents_expiring", "search_employee", "risk_signals", "pulse_summary"],
             {"/tahlil": ("hr_overview", {}), "/turnover": ("turnover", {}), "/shtat": ("headcount", {})},
             ("tahlil", "аналит", "текучест", "turnover", "штат", "headcount", "statist")),
    AgentDef("suhayl", "Employee helpdesk", "employee",
             ["my_card", "my_onboarding_plan", "my_documents", "create_my_request", "find_sop", "my_unread_sops", "ack_sop"],
             {"/menu": ("my_card", {}), "/jadval": ("my_card", {}), "/qoida": ("find_sop", {}), "/hujjat": ("my_documents", {})},
             ("отпуск", "ta'til", "tatil", "смена", "smena", "ariza", "заявк", "справк", "мой", "my ")),
    AgentDef("rauf", "Recruiter (HR mode)", "hr_head",
             ["vacancies_sla", "candidates", "vacancy_draft", "request_human_action"],
             {"/vacancy": ("vacancies_sla", {}), "/shortlist": ("candidates", {"status": "shortlist"}), "/sla": ("vacancies_sla", {})},
             ("ваканс", "vakans", "кандидат", "nomzod", "rezyume", "резюме", "shortlist")),
    AgentDef("reklama", "Channel ads negotiator (control panel)", "hr_head",
             ["ads_deals", "ads_add_channel", "vacancies_sla"],
             {"/holat": ("ads_deals", {})},
             ("reklama", "реклам", "канал", "kanal")),
]}


def route(text: str, default: str = "suhayl") -> str:
    """Hub-bot routing: one bot, many agents. '/agent name' or '@name' forces an agent."""
    t = text.lower()
    for name in AGENTS:
        if t.startswith(f"@{name}") or t.startswith(f"/{name}"):
            return name
    for a in AGENTS.values():
        if any(k in t for k in a.keywords):
            return a.name
    return default
