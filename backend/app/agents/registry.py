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
              "turnover", "vacancies_sla", "documents_expiring", "risk_signals", "pulse_summary", "discipline_ranking", "employee_month",
              "ask_agent", "request_human_action"],
             {"/hisobot": ("attendance_day", {}), "/davomat": ("attendance_day", {}), "/overview": ("hr_overview", {})},
             ("hisobot", "report", "kechik", "kech qol", "kech kel", "kim kel", "kelmadi", "kelmagan", "ishga kel", "опозда", "кто пришёл", "кто пришел", "не пришёл", "не пришел", "опозд", "intizom", "дисциплин", "tabel", "табел", "отчёт", "отчет", "davomat", "посещаем", "сводк")),
    AgentDef("ozoda", "Onboarding 30/60/90", "manager",
             ["search_employee", "onboarding_status", "onboarding_plan", "onboarding_add", "onboarding_score",
              "onboarding_mark_item", "find_sop", "onboarding_course_plan", "onboarding_course_start",
              "request_human_action"],
             {"/onboarding": ("onboarding_status", {}), "/sop": ("find_sop", {})},
             ("onboarding", "adapt", "video", "видео", "dars", "урок", "instruksiya", "инструкц", "o'rgat", "обучен", "адаптац", "новичок", "наставник", "mentor", "test", "тест", "sop")),
    AgentDef("bexruz", "Payroll pre-check", "manager",
             ["attendance_day", "attendance_rate", "overtime", "payroll_precheck", "payroll_summary", "discipline_ranking",
              "discipline_rules", "search_employee", "request_human_action"],
             {"/payrollcheck": ("payroll_precheck", {}), "/overtime": ("overtime", {}), "/attendance": ("attendance_rate", {"days": 7}),
              "/absent": ("attendance_day", {}), "/qoidalar": ("discipline_rules", {})},
             ("oylik", "зарплат", "payroll", "salary", "аванс", "штраф", "переработ", "overtime")),
    AgentDef("husayn", "HR analytics", "manager",
             ["headcount", "turnover", "attendance_day", "attendance_rate", "vacancies_sla", "onboarding_status",
              "documents_expiring", "search_employee", "risk_signals", "pulse_summary", "discipline_ranking", "weekly_signals"],
             {"/tahlil": ("hr_overview", {}), "/turnover": ("turnover", {}), "/shtat": ("headcount", {})},
             ("tahlil", "аналит", "текучест", "turnover", "штат", "headcount", "statist")),
    AgentDef("suhayl", "Employee helpdesk", "employee",
             ["my_card", "my_onboarding_plan", "my_documents", "create_my_request", "find_sop", "my_unread_sops", "ack_sop",
              "my_materials", "send_my_material"],
             {"/menu": ("my_card", {}), "/jadval": ("my_card", {}), "/qoida": ("find_sop", {}), "/hujjat": ("my_documents", {})},
             ("отпуск", "ta'til", "tatil", "смена", "smena", "ariza", "заявк", "справк", "мой", "my ")),
    AgentDef("rauf", "Recruiter (HR mode)", "hr_head",
             ["vacancies_sla", "candidates", "vacancy_draft", "interview_invite", "request_human_action"],
             {"/vacancy": ("vacancies_sla", {}), "/shortlist": ("candidates", {"status": "shortlist"}), "/sla": ("vacancies_sla", {})},
             ("ваканс", "vakans", "кандидат", "nomzod", "rezyume", "резюме", "shortlist")),
    AgentDef("reklama", "Channel ads negotiator (control panel)", "hr_head",
             ["ads_deals", "ads_add_channel", "vacancies_sla"],
             {"/holat": ("ads_deals", {})},
             ("reklama", "реклам", "канал", "kanal")),
    AgentDef("hr", "HR agent", "manager", []),
]}

# the single agent managers and HR talk to: every manager-side tool, de-duplicated (role gating still applies per tool)
AGENTS["hr"].tools = list(dict.fromkeys([t for n in ("hamza", "bexruz", "husayn", "ozoda", "rauf") for t in AGENTS[n].tools
                                         if t != "ask_agent"] + ["vacancies_list", "vacancy_write", "vacancy_publish", "hr_document", "sales_ranking", "hh_search", "interview_slots",
                                          "interview_slots_add", "job_offer", "new_hires", "attendance_by_department",
                                          "onboarding_today"]))
for _n in ("hamza", "bexruz", "husayn", "ozoda", "rauf"):
    AGENTS["hr"].commands.update(AGENTS[_n].commands)


def route(text: str, default: str = "suhayl") -> str:  # caller passes default="hamza" for managers/HR
    """Hub-bot routing: one bot, many agents. '/agent name' or '@name' forces an agent."""
    t = text.lower()
    for name in AGENTS:
        if t.startswith(f"@{name}") or t.startswith(f"/{name}"):
            return name
    for a in AGENTS.values():
        if any(k in t for k in a.keywords):
            return a.name
    return default
