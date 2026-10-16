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


@tool("headcount", "Headcount grouped by branch | region | position | status.", {"by": {**S, "enum": ["branch", "region", "position", "status"]}})
def _headcount(ctx: Ctx, by: str = "branch"):
    return analytics.headcount(ctx.db, ctx.scope, by)


@tool("turnover", "Turnover for 1..24 months, grouped; includes 'left in first 30 days'. Small groups shown as counts.",
      {"months": I, "by": {**S, "enum": ["branch", "region", "position"]}})
def _turnover(ctx: Ctx, months: int = 3, by: str = "branch"):
    return analytics.turnover(ctx.db, ctx.scope, max(1, min(months, 24)), by)


@tool("vacancies_sla", "Open vacancies with days open, SLA and traffic light.")
def _vac(ctx: Ctx):
    return analytics.vacancies_sla(ctx.db, ctx.scope)


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
            "note": "HR approves in the panel or with the ✅ button."}


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
