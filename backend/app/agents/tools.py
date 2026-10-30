"""Tool registry. Each tool declares a minimum role and whether it needs payroll access.
A tool above the user's role is never shown to the model."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import cfg
from ..models import AdDeal, Candidate, Employee, OnboardingPlan, Vacancy
from ..rbac import Scope, audit
from ..services import analytics, attendance, onboarding, payroll, people


@dataclass
class Ctx:
    db: Session
    scope: Scope
    agent: str
    depth: int = 0
    asked_agents: list[str] = field(default_factory=list)
    user_text: str = ""  # the person's own message in this turn (empty for agent-to-agent questions)


@dataclass
class Tool:
    name: str
    description: str
    params: dict
    fn: Callable[..., Any]
    min_role: str = "manager"
    needs_payroll: bool = False
    required: list[str] = field(default_factory=list)

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description,
                "input_schema": {"type": "object", "properties": self.params, "required": self.required}}


TOOLS: dict[str, Tool] = {}


def tool(name, description, params=None, min_role="manager", needs_payroll=False, required=None):
    def deco(fn):
        TOOLS[name] = Tool(name, description, params or {}, fn, min_role, needs_payroll, required or [])
        return fn
    return deco


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def _self(ctx: Ctx) -> Employee:
    if not ctx.scope.employee_id:
        raise PermissionError("Your Telegram is not linked to an employee card. Send /id to HR.")
    return ctx.db.get(Employee, ctx.scope.employee_id)


S = {"type": "string"}
I = {"type": "integer"}

# ---------------- manager-level (heads, regional, HR, owner) ----------------


@tool("hr_overview", "Today's HR overview in the user's branches: active staff, on shift, late, pending requests, new candidates.")
def _overview(ctx: Ctx):
    return analytics.overview(ctx.db, ctx.scope)


@tool("attendance_day", "Attendance for a day by branch. 'unmarked' does not mean absent.",
      {"date": {**S, "description": "YYYY-MM-DD, default today"}, "branch_id": I})
def _att_day(ctx: Ctx, date: str | None = None, branch_id: int | None = None):
    s = attendance.day_summary(ctx.db, ctx.scope, _d(date) or datetime.now().date(), branch_id)
    s["rows"] = [r for r in s["rows"] if r["status"] not in ("present", "off", "not_employed")][:30]
    return s


@tool("attendance_rate", "Attendance rate for the last N days (1..90) with top-10 by missed/late shifts.",
      {"days": I, "branch_id": I}, required=["days"])
def _att_rate(ctx: Ctx, days: int = 7, branch_id: int | None = None):
    return attendance.attendance_rate(ctx.db, ctx.scope, max(1, min(days, 90)), branch_id)


@tool("overtime", "Overtime per person for a month vs. schedule limit.", {"month": {**S, "description": "YYYY-MM"}})
def _overtime(ctx: Ctx, month: str | None = None):
    month = month or date.today().strftime("%Y-%m")
    t = attendance.month_tabel(ctx.db, ctx.scope, month)
    rows = sorted(({"full_name": r["full_name"], "branch": r["branch"], "overtime_hours": r["overtime_hours"]}
                   for r in t["rows"] if r["overtime_hours"]), key=lambda x: -x["overtime_hours"])
    return {"month": month, "limit_hours": cfg("attendance.overtime_limit_hours", 40), "rows": rows[:15]}


@tool("search_employee", "Find employees by name (Cyrillic/Latin) and/or position, within the user's branches. Max 8.",
      {"query": S, "position": S})
def _search(ctx: Ctx, query: str = "", position: str = ""):
    return people.search_employees(ctx.db, ctx.scope, query, position)


@tool("employee_card", "Employee card: position, branch, hire date, tenure, status.", {"employee_id": I}, required=["employee_id"])
def _card(ctx: Ctx, employee_id: int):
    emp = ctx.db.get(Employee, employee_id)
    if not emp:
        return {"error": "not found"}
    return people.employee_card(ctx.db, ctx.scope, emp)


@tool("discipline_ranking", "Month discipline per employee (from the timesheet / TimePay check-ins): late days, "
      "not-marked days, days needing review, worked vs norm hours. Worst first. 'Not marked' is not 'absent'.",
      {"month": {**S, "description": "YYYY-MM, default this month"}, "limit": I})
def _discipline(ctx: Ctx, month: str | None = None, limit: int = 15):
    month = month or date.today().strftime("%Y-%m")
    t = attendance.month_tabel(ctx.db, ctx.scope, month)
    rows = [{"full_name": r["full_name"], "position": r["position"], "late_days": r["late_days"],
             "not_marked_days": r["unknown_days"], "review_days": r["review_days"], "worked_hours": r["worked_hours"],
             "norm_hours": r["norm_hours"]} for r in t["rows"]]
    rows.sort(key=lambda x: -(x["late_days"] * 2 + x["not_marked_days"] + x["review_days"]))
    return {"month": month, "employees": len(rows), "rows": rows[:max(1, min(limit, 50))],
            "note": "not marked ≠ absent; a lead or HR confirms the reason"}


@tool("discipline_rules", "Company discipline rules: warnings before a fine, fine amount, counting window. Read only — "
      "a person applies a rule in the panel (a fine is a human-only deduction).")
def _discipline_rules(ctx: Ctx):
    from ..models import DisciplineRule
    from ..services import discipline
    return [{k: v for k, v in discipline.rule_dict(r).items() if k != "updated_by"}
            for r in ctx.db.scalars(select(DisciplineRule).order_by(DisciplineRule.id))]


@tool("employee_month", "One employee's attendance for a month: each day's status, check-in/out, hours, lateness.",
      {"employee_id": I, "month": {**S, "description": "YYYY-MM"}}, required=["employee_id"])
def _employee_month(ctx: Ctx, employee_id: int, month: str | None = None):
    emp = ctx.db.get(Employee, employee_id)
    if not emp or not ctx.scope.allows_branch(emp.branch_id):
        return {"error": "not found"}
    month = month or date.today().strftime("%Y-%m")
    t = attendance.month_tabel(ctx.db, ctx.scope, month, emp.branch_id)
    row = next((r for r in t["rows"] if r["employee_id"] == emp.id), None)
    if not row:
        return {"error": "no timesheet row for this month"}
    days = [{"day": str(d), "code": c["c"], "hours": c["h"], "late_min": c.get("l")}
            for d, c in zip(t["days"], row["cells"]) if c["c"] not in ("", "-")]
    return {"full_name": emp.full_name, "month": month, "worked_hours": row["worked_hours"], "norm_hours": row["norm_hours"],
            "late_days": row["late_days"], "not_marked_days": row["unknown_days"], "days": days}


@tool("payroll_summary", "Month payroll per employee: accrued, KPI, bonus, penalties, advances, to pay, and the fund. "
      "Shows numbers only — approval is a human action.", {"month": {**S, "description": "YYYY-MM"}}, needs_payroll=True)
def _payroll_summary(ctx: Ctx, month: str | None = None):
    month = month or date.today().strftime("%Y-%m")
    t = payroll.payroll_table(ctx.db, ctx.scope, month)
    keep = ("full_name", "position", "base", "accrued", "kpi", "bonus", "penalty", "advance", "total")
    return {"month": month, "status": t["status"], "fund": t["fund"], "unknown_salary": t["unknown_salary"],
            "rows": [{k: r.get(k) for k in keep} for r in t["rows"]][:40]}


@tool("headcount", "Headcount grouped by branch | region | position | status | department.",
      {"by": {**S, "enum": ["branch", "region", "position", "status", "department"]}})
def _headcount(ctx: Ctx, by: str = "branch"):
    return analytics.headcount(ctx.db, ctx.scope, by)


@tool("turnover", "Turnover for 1..24 months, grouped; includes 'left in first 30 days'. Small groups shown as counts.",
      {"months": I, "by": {**S, "enum": ["branch", "region", "position"]}})
def _turnover(ctx: Ctx, months: int = 3, by: str = "branch"):
    return analytics.turnover(ctx.db, ctx.scope, max(1, min(months, 24)), by)


@tool("weekly_signals", "Per-branch signals: lateness, confirmed absences and early leaves in the last 7 days vs the average "
      "week of the 4 weeks before (>= 3 cases and >= 2x). A reason to talk, never a decision. In a group chat give only the count.")
def _weekly_signals(ctx: Ctx):
    return analytics.weekly_signals(ctx.db, ctx.scope)


@tool("vacancies_sla", "Open vacancies with days open, SLA and traffic light.")
def _vac(ctx: Ctx):
    return analytics.vacancies_sla(ctx.db, ctx.scope)


@tool("vacancies_list", "All vacancies incl. DRAFTS: id, title, status, salary, schedule, branch, missing fields.")
def _vac_list(ctx: Ctx):
    from ..services import vacancies
    rows = ctx.db.scalars(select(Vacancy).where(Vacancy.status != "closed", Vacancy.is_template.is_(False))
                          .order_by(Vacancy.id.desc()).limit(30))
    return [{"id": v.id, "title": v.title, "status": v.status, "salary": v.salary_text, "schedule": v.schedule_text,
             "branch_id": v.branch_id, "missing": vacancies.missing(v)} for v in rows
            if v.branch_id is None or ctx.scope.allows_branch(v.branch_id)]


@tool("hr_document", "Issue an HR document as PDF from a template and send the file to the asker in Telegram. "
      "Templates: employment_certificate (ish joyidan ma'lumotnoma), hire_order, leave_order (extra: leave_from, leave_to, "
      "leave_days). Find the employee with search_employee first. Unknown fields stay blank and are listed — never invent.",
      {"template_code": S, "employee_id": I, "extra": {"type": "object"}}, min_role="hr_head", required=["template_code", "employee_id"])
def _hr_doc(ctx: Ctx, template_code: str, employee_id: int, extra: dict | None = None):
    from ..config import ROOT
    from ..models import DocTemplate, Outbox
    from ..services import docgen
    docgen.ensure_templates(ctx.db)
    t = ctx.db.scalar(select(DocTemplate).where(DocTemplate.code == template_code, DocTemplate.active.is_(True)))
    emp = ctx.db.get(Employee, employee_id)
    if not t or not emp:
        return {"error": "template or employee not found"}
    try:
        d = docgen.issue(ctx.db, ctx.scope, t, emp, {k: str(v) for k, v in (extra or {}).items()})
    except PermissionError:
        return {"error": "not your branch"}
    sent = False
    if ctx.scope.actor.startswith("tg:"):
        out = ROOT / "data" / "uploads" / "docs"
        out.mkdir(parents=True, exist_ok=True)
        f = out / f"{d.number}.pdf"
        f.write_bytes(docgen.pdf(d))
        ctx.db.add(Outbox(telegram_id=int(ctx.scope.actor[3:]), text=f"{d.title} · {d.number} · {emp.full_name}", file_path=str(f)))
        sent = True
    ctx.db.commit()
    return {"number": d.number, "missing_fields": d.missing, "pdf_sent_to_chat": sent}


@tool("documents_expiring", "Certificates / medical books / check-ups expiring within N days.", {"days": I})
def _docs(ctx: Ctx, days: int = 30):
    return people.expiring_documents(ctx.db, ctx.scope, days)[:30]


@tool("onboarding_status", "Onboarding 30/60/90 status with traffic light, mentor, test scores.")
def _onb_status(ctx: Ctx):
    s = onboarding.status(ctx.db, ctx.scope)
    for p in s["plans"]:
        p.pop("items", None)
    return s


@tool("onboarding_plan", "One person's 30/60/90 plan with checklist item ids.", {"employee_id": I}, required=["employee_id"])
def _onb_plan(ctx: Ctx, employee_id: int):
    p = ctx.db.scalar(select(OnboardingPlan).where(OnboardingPlan.employee_id == employee_id))
    if not p or not ctx.scope.allows_branch(p.employee.branch_id):
        return {"error": "no plan in your branches"}
    return onboarding.plan_card(p)


@tool("onboarding_add", "Add an employee to onboarding (creates checklist from position template). HR only.",
      {"employee_id": I, "mentor": S, "start_date": S}, min_role="hr_head", required=["employee_id"])
def _onb_add(ctx: Ctx, employee_id: int, mentor: str | None = None, start_date: str | None = None):
    emp = ctx.db.get(Employee, employee_id)
    if not emp:
        return {"error": "not found"}
    return onboarding.plan_card(onboarding.create_plan(ctx.db, ctx.scope, emp, mentor, _d(start_date)))


@tool("onboarding_score", "Record a 0..100 test score for the current (or given) stage.",
      {"employee_id": I, "score": I, "stage": {"type": "integer", "enum": [30, 60, 90]}}, required=["employee_id", "score"])
def _onb_score(ctx: Ctx, employee_id: int, score: int, stage: int | None = None):
    p = ctx.db.scalar(select(OnboardingPlan).where(OnboardingPlan.employee_id == employee_id))
    if not p:
        return {"error": "no plan"}
    return onboarding.record_score(ctx.db, ctx.scope, p, score, stage)


@tool("onboarding_mark_item", "Mark a checklist item done (or undone).", {"item_id": I, "done": {"type": "boolean"}}, required=["item_id"])
def _onb_mark(ctx: Ctx, item_id: int, done: bool = True):
    i = onboarding.mark_item(ctx.db, ctx.scope, item_id, done)
    return {"item_id": i.id, "done": i.done}


@tool("payroll_precheck", "Pre-payout check for a month: issues and amount that could be paid wrong. Never approves.",
      {"month": {**S, "description": "YYYY-MM"}}, min_role="hr_head", needs_payroll=True)
def _precheck(ctx: Ctx, month: str | None = None):
    month = month or date.today().strftime("%Y-%m")
    r = payroll.precheck(ctx.db, ctx.scope, month)
    r["issues"] = r["issues"][:25]
    return r


@tool("request_human_action", "Create an approval request for a human-only decision "
      "(payroll_approve, deduction_create, contract_change, hire, fire, mass_broadcast, request_approve). You can NOT do these yourself.",
      {"action": S, "summary": S}, required=["action", "summary"])
def _human(ctx: Ctx, action: str, summary: str):
    a = people.request_human_action(ctx.db, ctx.scope, action, f"[{ctx.agent}] {summary}")
    return {"approval_id": a.id, "status": "pending", "note": "A person will decide."}


@tool("ask_agent", "Ask another HR agent (ozoda, bexruz, husayn) a question. Max 3 per answer.",
      {"agent": {**S, "enum": ["ozoda", "bexruz", "husayn"]}, "question": S}, required=["agent", "question"])
def _ask(ctx: Ctx, agent: str, question: str):
    from .runtime import run_agent
    if ctx.depth >= 1 or len(ctx.asked_agents) >= 3:
        return {"error": "limit: max 3 agents, no nested delegation"}
    ctx.asked_agents.append(agent)
    return {"agent": agent, "answer": run_agent(ctx.db, agent, ctx.scope, question, user_key=f"{ctx.agent}->{agent}", depth=1)}


# ---------------- employee self-service (Suhayl) — self only, hard-wired ----------------


@tool("my_card", "The user's own card: position, branch, leave balance, today's shift, last 5 requests.", min_role="employee")
def _my_card(ctx: Ctx):
    emp = _self(ctx)
    card = people.employee_card(ctx.db, ctx.scope, emp)
    card["shift_today"] = people.shift_today(emp)
    card["requests"] = people.list_requests(ctx.db, Scope(ctx.scope.actor, "owner"), employee_id=emp.id)[:5]
    return card


@tool("my_onboarding_plan", "The user's OWN 30/60/90 plan. Cannot be used for colleagues.", min_role="employee")
def _my_plan(ctx: Ctx):
    return onboarding.my_plan(ctx.db, ctx.scope) or {"info": "no onboarding plan"}


@tool("my_documents", "The user's own documents and expiry dates.", min_role="employee")
def _my_docs(ctx: Ctx):
    return people.my_documents(ctx.db, _self(ctx))


@tool("create_my_request", "Create a request for the user: vacation | certificate | shift_swap | sick_leave | other. Always 'pending'.",
      {"kind": S, "date_from": S, "date_to": S, "comment": S}, min_role="employee", required=["kind"])
def _my_req(ctx: Ctx, kind: str, date_from: str | None = None, date_to: str | None = None, comment: str = ""):
    try:
        r = people.create_request(ctx.db, ctx.scope, _self(ctx), kind, _d(date_from), _d(date_to), comment, channel="suhayl")
    except ValueError as e:
        return {"error": str(e)}
    return {"request_id": r.id, "status": r.status, "note": "A manager decides, not the bot."}


@tool("find_sop", "Search the SOP / rules library by keyword; defaults to the user's position. Never invent rule text.",
      {"query": S, "position_code": S}, min_role="employee")
def _sop(ctx: Ctx, query: str = "", position_code: str | None = None):
    if not position_code and ctx.scope.employee_id:
        emp = ctx.db.get(Employee, ctx.scope.employee_id)
        position_code = emp.position.code if emp and emp.position else None
    res = people.find_sops(ctx.db, query, position_code)
    return res or {"info": "no SOP found for this role/topic yet"}


@tool("my_unread_sops", "Rules (SOPs) for the user's position that they have not confirmed reading yet (current version).",
      min_role="employee")
def _my_unread(ctx: Ctx):
    from ..services import engagement
    return engagement.my_unread(ctx.db, _self(ctx)) or {"info": "all rules are confirmed"}


@tool("ack_sop", "Record that the user has read a rule (SOP) — only after they explicitly say they read it.",
      {"sop_id": I}, min_role="employee", required=["sop_id"])
def _ack(ctx: Ctx, sop_id: int):
    from ..services import engagement
    return engagement.acknowledge(ctx.db, ctx.scope, _self(ctx), sop_id)


@tool("risk_signals", "Turnover-risk signals (explainable rules) for HR. A reason to talk to the person, never a decision.",
      min_role="hr_head")
def _risk(ctx: Ctx):
    from ..services import engagement
    return engagement.risk_signals(ctx.db, ctx.scope)[:20]


@tool("pulse_summary", "Anonymous eNPS and exit-survey summary (shown only for groups of 5+ answers).")
def _pulse(ctx: Ctx, months: int = 3):
    from ..services import engagement
    return engagement.pulse_summary(ctx.db, ctx.scope, months)


# ---------------- recruiting (Rauf HR mode) & ads ----------------


@tool("candidates", "Candidates list (optionally by vacancy/status) with score and label.",
      {"vacancy_id": I, "status": S}, min_role="hr_head")
def _cands(ctx: Ctx, vacancy_id: int | None = None, status: str | None = None):
    q = select(Candidate).order_by(Candidate.score.desc().nulls_last())
    if vacancy_id:
        q = q.where(Candidate.vacancy_id == vacancy_id)
    if status:
        q = q.where(Candidate.status == status)
    return [{"id": c.id, "full_name": c.full_name, "vacancy": c.vacancy.title if c.vacancy else None, "score": c.score,
             "label": c.label, "status": c.status} for c in ctx.db.scalars(q.limit(30))]


@tool("vacancy_draft", "Create a vacancy DRAFT from HR's words. Required: title, branch_id, salary_text, schedule_text. "
      "Never invent salary or phones — leave empty and ask.",
      {"title": S, "branch_id": I, "position_code": S, "salary_text": S, "schedule_text": S, "requirements": S},
      min_role="hr_head", required=["title"])
def _vac_draft(ctx: Ctx, title: str, branch_id: int | None = None, position_code: str | None = None,
               salary_text: str | None = None, schedule_text: str | None = None, requirements: str = ""):
    from ..services import recruiting
    v = Vacancy(title=title, branch_id=branch_id, position_code=position_code, salary_text=salary_text,
                schedule_text=schedule_text, requirements=requirements)
    ctx.db.add(v)
    ctx.db.flush()
    audit(ctx.db, ctx.scope, "vacancy_draft", f"vacancy:{v.id}")
    miss = recruiting.missing_fields({"title": title, "branch": branch_id, "salary_text": salary_text, "schedule_text": schedule_text})
    return {"vacancy_id": v.id, "status": "draft", "missing": miss, "preview": recruiting.render_ad(v),
            "note": "HR approves in the panel or by writing the confirm word (e.g. e'lon qil)."}


@tool("vacancy_write", "Write a vacancy post from HR's words (agent fills a fixed template; never invents salary, phones, "
      "links). Returns the draft id and text; missing fields are listed.", {"brief": S}, min_role="hr_head", required=["brief"])
def _vac_write(ctx: Ctx, brief: str):
    from ..services import vacancies
    v = vacancies.from_brief(ctx.db, ctx.scope, brief)
    ctx.db.commit()
    return {"vacancy_id": v.id, "text": v.ad_text, "missing": vacancies.missing(v),
            "next": "HR: say what to change, or 'e'lon qil' to publish"}


@tool("vacancy_publish", "Publish a vacancy draft (bot list + public jobs page). Works only when HR's own message is "
      "exactly the confirm word (e.g. \"e'lon qil\") — checked in code; otherwise ask HR to write it.",
      {"vacancy_id": I}, min_role="hr_head", required=["vacancy_id"])
def _vac_publish(ctx: Ctx, vacancy_id: int):
    from ..services import vacancies
    if not vacancies.is_confirm(ctx.user_text):
        return {"error": "not published: HR must write exactly one of " + ", ".join(vacancies.confirm_words())}
    v = ctx.db.get(Vacancy, vacancy_id)
    if not v:
        return {"error": "not found"}
    try:
        done = vacancies.publish(ctx.db, ctx.scope, v, web=True)
    except ValueError as e:
        return {"error": str(e), "missing": vacancies.missing(v)}
    ctx.db.commit()
    return {"published": sorted(done), "jobs_page": True}


@tool("ads_deals", "Ad placement deals in Telegram channels by stage.", min_role="hr_head")
def _deals(ctx: Ctx):
    return [{"id": d.id, "channel": d.channel, "subscribers": d.subscribers, "stage": d.stage, "price": d.price,
             "budget": d.budget} for d in ctx.db.scalars(select(AdDeal).order_by(AdDeal.created_at.desc()).limit(30))]


@tool("ads_add_channel", "Register a channel candidate for a vacancy with a per-post budget (UZS). Does NOT message anyone.",
      {"channel": S, "vacancy_id": I, "budget": I, "subscribers": I}, min_role="hr_head", required=["channel", "budget"])
def _ads_add(ctx: Ctx, channel: str, budget: int, vacancy_id: int | None = None, subscribers: int | None = None):
    lo, hi = int(cfg("ads.budget_min", 10000)), int(cfg("ads.budget_max", 100000000))
    if not lo <= budget <= hi:
        return {"error": f"budget must be {lo}..{hi}"}
    d = AdDeal(channel=channel.strip(), vacancy_id=vacancy_id, budget=budget, subscribers=subscribers)
    ctx.db.add(d)
    ctx.db.flush()
    note = "Budget above confirm threshold — owner must confirm." if budget > int(cfg("ads.budget_confirm_above", 2000000)) else ""
    return {"deal_id": d.id, "stage": d.stage, "note": note or "First message is sent only after a person presses 'Write'."}


def tools_for(names: list[str], scope: Scope) -> list[Tool]:
    out = []
    for n in names:
        t = TOOLS[n]
        if not scope.at_least(t.min_role):
            continue
        if t.needs_payroll and not scope.payroll:
            continue
        out.append(t)
    return out


def execute(ctx: Ctx, t: Tool, args: dict) -> str:
    try:
        res = t.fn(ctx, **(args or {}))
        ctx.db.flush()
    except (PermissionError, ValueError, people.AccessDenied, onboarding.NotAllowed) as e:
        res = {"error": str(e)}
    audit(ctx.db, ctx.scope, "tool_call", t.name, agent=ctx.agent, args=args)
    return json.dumps(res, ensure_ascii=False, default=str)[:12000]


# ---------------- onboarding course (video lessons / instructions from the library) ----------------

@tool("my_materials", "The user's OWN onboarding materials (videos, instructions): what was sent, viewed, planned.",
      min_role="employee")
def _my_materials(ctx: Ctx):
    from ..services import onboarding_media
    return {"items": onboarding_media.my_materials(ctx.db, _self(ctx))}


@tool("send_my_material", "Send one of the user's OWN onboarding materials again to their Telegram (by send_id from my_materials).",
      {"send_id": I}, min_role="employee", required=["send_id"])
def _send_my_material(ctx: Ctx, send_id: int):
    from ..services import onboarding_media
    ok = onboarding_media.resend(ctx.db, _self(ctx), send_id)
    ctx.db.commit()
    return {"ok": ok}


@tool("interview_invite", "Invite a candidate to an interview: the bot sends them the free time slots, they answer with a "
      "number. Needs free slots added by HR.", {"candidate_id": I}, min_role="hr_head", required=["candidate_id"])
def _interview_invite(ctx: Ctx, candidate_id: int):
    from ..services import hiring
    c = ctx.db.get(Candidate, candidate_id)
    if not c:
        return {"error": "not found"}
    try:
        out = hiring.invite(ctx.db, ctx.scope, c)
    except ValueError as e:
        return {"error": str(e)}
    ctx.db.commit()
    return out


@tool("onboarding_course_plan", "Propose an onboarding course for an employee: library videos/instructions that fit their "
      "position and department, with day and reason. Nothing is sent.", {"employee_id": I}, required=["employee_id"])
def _course_plan(ctx: Ctx, employee_id: int):
    from ..services import onboarding_media
    e = ctx.db.get(Employee, employee_id)
    if not e or not ctx.scope.allows_branch(e.branch_id):
        return {"error": "not found"}
    return {"employee": e.full_name, "profile": onboarding_media.profile(e), "items": onboarding_media.plan(ctx.db, e)}


@tool("onboarding_course_start", "Start the proposed onboarding course for an employee (schedules it; day-0 items are sent now). "
      "Use after onboarding_course_plan when HR asked to start it.", {"employee_id": I}, min_role="hr_head", required=["employee_id"])
def _course_start(ctx: Ctx, employee_id: int):
    from ..services import onboarding_media
    e = ctx.db.get(Employee, employee_id)
    if not e or not ctx.scope.allows_branch(e.branch_id):
        return {"error": "not found"}
    n = onboarding_media.assign(ctx.db, ctx.scope, e, onboarding_media.plan(ctx.db, e))
    sent = onboarding_media.deliver_due(ctx.db)
    ctx.db.commit()
    return {"scheduled": n, "sent_now": sent, "telegram_linked": e.telegram_id is not None}
