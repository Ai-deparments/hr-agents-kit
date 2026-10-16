"""Employees, requests, documents, SOP library, human-only approvals."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import cfg
from ..models import Absence, ApprovalRequest, Document, Employee, LeaveRequest, Sop
from ..rbac import Scope, audit
from . import schedules as sch

# Cyrillic -> Latin (uz/ru) so "Дилноза" finds "Dilnoza"; h/x treated alike.
_CYR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюяўқғҳ",
                ["a", "b", "v", "g", "d", "e", "yo", "j", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u",
                 "f", "x", "ts", "ch", "sh", "sh", "", "i", "", "e", "yu", "ya", "o'", "q", "g'", "h"]))


def norm_name(s: str) -> str:
    s = "".join(_CYR.get(ch, ch) for ch in s.lower())
    s = s.replace("ʻ", "'").replace("‘", "'").replace("’", "'").replace("h", "x")
    return re.sub(r"[^a-z0-9' ]", "", s)


class AccessDenied(Exception):
    pass


def employee_card(db: Session, scope: Scope, emp: Employee) -> dict:
    if not scope.allows_branch(emp.branch_id) and scope.employee_id != emp.id:
        audit(db, scope, "access_denied", f"employee:{emp.id}")
        raise AccessDenied("This person is not in your branches")
    today = date.today()
    tenure = (today - emp.hire_date).days if emp.hire_date else None
    card = {"id": emp.id, "full_name": emp.full_name, "position": emp.position.title if emp.position else None,
            "branch": emp.branch.name if emp.branch else None, "branch_id": emp.branch_id,
            "region": emp.branch.region.name if emp.branch and emp.branch.region else None,
            "hire_date": emp.hire_date.isoformat() if emp.hire_date else None, "tenure_days": tenure,
            "status": emp.status, "pay_type": emp.pay_type, "schedule": emp.schedule_code,
            "leave_balance_days": emp.leave_balance_days, "phone": emp.phone if scope.role != "employee" else None,
            "telegram_linked": emp.telegram_id is not None}
    if scope.payroll:
        card["base_salary"] = emp.base_salary
    return card


def search_employees(db: Session, scope: Scope, query: str = "", position: str = "", branch_id: int | None = None,
                     include_fired: bool = False, limit: int = 8) -> list[dict]:
    q = select(Employee)
    if scope.branch_ids is not None:
        q = q.where(Employee.branch_id.in_(scope.branch_ids or {-1}))
    if branch_id:
        q = q.where(Employee.branch_id == branch_id)
    if not include_fired:
        q = q.where(Employee.status != "fired")
    res = []
    nq, np_ = norm_name(query), norm_name(position)
    for e in db.scalars(q.order_by(Employee.full_name)):
        if nq and not all(part in norm_name(e.full_name) for part in nq.split()):
            continue
        if np_ and (not e.position or np_ not in norm_name(e.position.title)):
            continue
        res.append({"id": e.id, "full_name": e.full_name, "position": e.position.title if e.position else None,
                    "branch": e.branch.name if e.branch else None, "status": e.status,
                    "hire_date": e.hire_date.isoformat() if e.hire_date else None})
        if len(res) >= limit:
            break
    return res


# ---------- requests (vacation, certificate, shift swap, sick leave ...) ----------

def create_request(db: Session, scope: Scope, emp: Employee, kind: str, date_from: date | None = None,
                   date_to: date | None = None, comment: str = "", channel: str = "panel") -> LeaveRequest:
    kinds = cfg("requests.kinds", ["vacation", "certificate", "other"])
    if kind not in kinds:
        kind = "other"
    days = None
    if date_from and date_to:
        if date_to < date_from:
            raise ValueError("date_to is before date_from")
        days = float((date_to - date_from).days + 1)
    if kind == "vacation":
        if days is None:
            raise ValueError("Vacation needs dates")
        bal = emp.leave_balance_days
        if bal is not None and days > bal:
            raise ValueError(f"You ask for {days:g} days, your balance is {bal:g}")
        # Labor Code: annual leave is due after N months of work; earlier only by agreement — flag it for the approver
        months = int(cfg("labor.leave_after_months", 6))
        if emp.hire_date and (date_from - emp.hire_date).days < months * 30:
            comment = f"[!] Less than {months} months of service — early leave only by agreement. " + comment
    r = LeaveRequest(employee_id=emp.id, kind=kind, date_from=date_from, date_to=date_to, days=days,
                     comment=comment[:1000], channel=channel)
    db.add(r)
    db.flush()
    audit(db, scope, "request_create", f"request:{r.id}", kind=kind, days=days)
    return r


def list_requests(db: Session, scope: Scope, status: str | None = None, employee_id: int | None = None) -> list[dict]:
    q = select(LeaveRequest).join(Employee).order_by(LeaveRequest.created_at.desc())
    if scope.branch_ids is not None:
        q = q.where(Employee.branch_id.in_(scope.branch_ids or {-1}))
    if status:
        q = q.where(LeaveRequest.status == status)
    if employee_id:
        q = q.where(LeaveRequest.employee_id == employee_id)
    return [{"id": r.id, "employee_id": r.employee_id, "full_name": r.employee.full_name,
             "branch": r.employee.branch.name if r.employee.branch else None, "kind": r.kind,
             "date_from": r.date_from.isoformat() if r.date_from else None,
             "date_to": r.date_to.isoformat() if r.date_to else None, "days": r.days, "comment": r.comment,
             "status": r.status, "channel": r.channel, "decided_by": r.decided_by,
             "decision_reason": r.decision_reason, "created_at": r.created_at.isoformat(timespec="minutes")}
            for r in db.scalars(q.limit(300))]


def decide_request(db: Session, scope: Scope, request_id: int, approve: bool, reason: str) -> LeaveRequest:
    """Human only. Approved vacation / sick leave lands in the tabel automatically."""
    if scope.actor.startswith("agent:"):
        raise AccessDenied("Agents cannot approve requests")
    r = db.get(LeaveRequest, request_id)
    if not r:
        raise ValueError("Request not found")
    if not scope.allows_branch(r.employee.branch_id):
        raise AccessDenied("Not your branch")
    if r.status != "pending":
        raise ValueError("Already decided")
    if len(reason.strip()) < 3:
        raise ValueError("Reason is required")
    r.status = "approved" if approve else "rejected"
    r.decided_by, r.decision_reason, r.decided_at = scope.actor, reason, datetime.now()
    if approve and r.kind in ("vacation", "sick_leave") and r.date_from and r.date_to:
        db.add(Absence(employee_id=r.employee_id, kind=r.kind, date_from=r.date_from, date_to=r.date_to, request_id=r.id))
        if r.kind == "vacation" and r.employee.leave_balance_days is not None and r.days:
            r.employee.leave_balance_days -= r.days
    audit(db, scope, "request_decide", f"request:{r.id}", status=r.status, reason=reason)
    return r


# ---------- approvals for agent-requested human-only actions ----------

def request_human_action(db: Session, scope: Scope, action: str, summary: str, payload: dict | None = None,
                         branch_id: int | None = None) -> ApprovalRequest:
    allowed = cfg("human_only_actions", [])
    if action not in allowed:
        raise ValueError(f"Unknown human-only action: {action}")
    a = ApprovalRequest(action=action, summary=summary[:400], payload=payload or {}, branch_id=branch_id,
                        requested_by=scope.actor)
    db.add(a)
    db.flush()
    audit(db, scope, "approval_requested", f"approval:{a.id}", action=action)
    return a


def decide_approval(db: Session, scope: Scope, approval_id: int, approve: bool, reason: str) -> ApprovalRequest:
    if scope.actor.startswith("agent:"):
        raise AccessDenied("Agents cannot decide")
    a = db.get(ApprovalRequest, approval_id)
    if not a or a.status != "pending":
        raise ValueError("Not found or already decided")
    if not scope.allows_branch(a.branch_id) and a.branch_id is not None:
        raise AccessDenied("Not your branch")
    if len(reason.strip()) < 3:
        raise ValueError("Reason is required")
    a.status = "approved" if approve else "rejected"
    a.decided_by, a.decision_reason, a.decided_at = scope.actor, reason, datetime.now()
    audit(db, scope, "approval_decide", f"approval:{a.id}", status=a.status)
    return a


# ---------- documents with expiry ----------

def expiring_documents(db: Session, scope: Scope, days: int = 30, today: date | None = None) -> list[dict]:
    today = today or date.today()
    titles = {t["code"]: t["title"] for t in cfg("documents.types", [])}
    q = select(Document).join(Employee).where(Document.expires.is_not(None),
                                             Document.expires <= today + timedelta(days=days), Employee.status != "fired")
    if scope.branch_ids is not None:
        q = q.where(Employee.branch_id.in_(scope.branch_ids or {-1}))
    if scope.role == "employee":
        q = q.where(Document.employee_id == scope.employee_id)
    out = []
    for d in db.scalars(q.order_by(Document.expires)):
        out.append({"id": d.id, "employee_id": d.employee_id, "full_name": d.employee.full_name,
                    "branch": d.employee.branch.name if d.employee.branch else None, "doc_type": d.doc_type,
                    "title": titles.get(d.doc_type, d.doc_type), "expires": d.expires.isoformat(),
                    "days_left": (d.expires - today).days, "expired": d.expires < today})
    return out


def my_documents(db: Session, emp: Employee) -> list[dict]:
    titles = {t["code"]: t["title"] for t in cfg("documents.types", [])}
    return [{"title": titles.get(d.doc_type, d.doc_type), "expires": d.expires.isoformat() if d.expires else None,
             "days_left": (d.expires - date.today()).days if d.expires else None}
            for d in db.scalars(select(Document).where(Document.employee_id == emp.id))]


# ---------- SOP library (one library for all agents + panel) ----------

def find_sops(db: Session, query: str = "", position_code: str | None = None, limit: int = 10) -> list[dict]:
    q = select(Sop)
    if position_code:
        q = q.where(or_(Sop.position_code == position_code, Sop.position_code.is_(None)))
    items = list(db.scalars(q))
    if query:
        words = [w for w in norm_name(query).split() if len(w) > 2]
        scored = []
        for s in items:
            hay = norm_name(f"{s.title} {s.tags} {s.body}")
            score = sum(hay.count(w) for w in words)
            if score:
                scored.append((score, s))
        items = [s for _, s in sorted(scored, key=lambda x: -x[0])]
    return [{"id": s.id, "title": s.title, "position": s.position_code, "excerpt": s.body[:600]} for s in items[:limit]]


def shift_today(emp: Employee, d: date | None = None) -> dict:
    d = d or date.today()
    start = sch.planned_start(emp, d)
    if not start:
        return {"date": d.isoformat(), "working": False}
    end = start + timedelta(hours=sch.planned_hours(emp, d))
    return {"date": d.isoformat(), "working": True, "start": start.strftime("%H:%M"),
            "end": end.strftime("%H:%M") + (" (+1 day)" if end.date() > d else "")}
