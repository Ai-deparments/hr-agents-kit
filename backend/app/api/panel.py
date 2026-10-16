"""Web HR panel API (office, HR, payroll, executives, regional managers)."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import check_password, current_user, make_token, panel_scope, require
from ..config import cfg
from ..db import get_db
from ..models import (ApprovalRequest, AuditLog, Branch, BranchLead, Candidate, ChatMessage, Document, Employee, HrOverride,
                      OnboardingPlan, PayrollEntry, Position, Region, SalesRecord, Sop, User, Vacancy)
from ..rbac import Scope, audit
from ..services import analytics, attendance, onboarding, payroll, people, recruiting, reports

router = APIRouter(prefix="/api")


def _month(m: str | None) -> str:
    return m or date.today().strftime("%Y-%m")


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except (people.AccessDenied, onboarding.NotAllowed, PermissionError) as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------- auth & meta ----------------

class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if not user or not user.active or not check_password(user, body.password):
        raise HTTPException(401, "Wrong login or password")
    audit(db, Scope(f"user:{user.username}", user.role), "login")
    db.commit()
    return {"token": make_token(str(user.id), "panel", 30)}


@router.get("/me")
def me(user: User = Depends(current_user), scope: Scope = Depends(panel_scope)):
    return {"username": user.username, "full_name": user.full_name, "role": user.role,
            "branch_scope": None if scope.branch_ids is None else sorted(scope.branch_ids),
            "payroll": scope.payroll, "perms": sorted(scope.perms)}


@router.get("/config/public")
def public_config():
    return {"company": cfg("company"), "branding": cfg("branding"), "request_kinds": cfg("requests.kinds"),
            "documents": cfg("documents.types"), "human_only_actions": cfg("human_only_actions")}


@router.get("/dictionaries")
def dictionaries(scope: Scope = Depends(panel_scope), db: Session = Depends(get_db)):
    branches = [b for b in db.scalars(select(Branch).order_by(Branch.name)) if scope.allows_branch(b.id)]
    return {"regions": [{"id": r.id, "code": r.code, "name": r.name} for r in db.scalars(select(Region))],
            "branches": [{"id": b.id, "code": b.code, "name": b.name, "region_id": b.region_id, "city": b.city, "mode": b.mode}
                         for b in branches],
            "positions": [{"id": p.id, "code": p.code, "title": p.title} for p in db.scalars(select(Position))],
            "schedules": list((cfg("schedules") or {}).keys())}


@router.get("/dashboard")
def dashboard(scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    o = analytics.overview(db, scope)
    o["onboarding"] = {k: v for k, v in onboarding.status(db, scope).items() if k != "plans"}
    o["documents_30d"] = len(people.expiring_documents(db, scope, 30))
    o["pending_approvals"] = len(list(db.scalars(select(ApprovalRequest.id).where(ApprovalRequest.status == "pending"))))
    o["vacancies"] = analytics.vacancies_sla(db, scope)[:5]
    return o


# ---------------- employees ----------------

class EmployeeIn(BaseModel):
    full_name: str = Field(min_length=3)
    phone: str | None = None
    branch_id: int
    position_id: int | None = None
    hire_date: date | None = None
    status: str = "probation"
    pay_type: str = "monthly"
    base_salary: int | None = None
    schedule_code: str = "day_9_18"
    leave_balance_days: float | None = None
    telegram_id: int | None = None


def _emp_row(e: Employee, scope: Scope) -> dict:
    return {"id": e.id, "full_name": e.full_name, "phone": e.phone, "branch_id": e.branch_id,
            "branch": e.branch.name if e.branch else None, "position_id": e.position_id,
            "position": e.position.title if e.position else None, "hire_date": e.hire_date, "fire_date": e.fire_date,
            "status": e.status, "pay_type": e.pay_type, "schedule_code": e.schedule_code,
            "leave_balance_days": e.leave_balance_days, "telegram_linked": e.telegram_id is not None,
            "base_salary": e.base_salary if scope.payroll else None}


@router.get("/employees")
def employees(q: str = "", branch_id: int | None = None, status: str | None = None,
              scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    stmt = select(Employee).order_by(Employee.full_name)
    if scope.branch_ids is not None:
        stmt = stmt.where(Employee.branch_id.in_(scope.branch_ids or {-1}))
    if branch_id:
        stmt = stmt.where(Employee.branch_id == branch_id)
    if status:
        stmt = stmt.where(Employee.status == status)
    nq = people.norm_name(q)
    rows = [e for e in db.scalars(stmt) if not nq or nq in people.norm_name(f"{e.full_name} {e.phone or ''} {e.position.title if e.position else ''}")]
    return [_emp_row(e, scope) for e in rows]


@router.post("/employees")
def create_employee(body: EmployeeIn, scope: Scope = Depends(require("hr.write")), db: Session = Depends(get_db)):
    if not scope.allows_branch(body.branch_id):
        raise HTTPException(403, "You can add people only to your branches")
    data = body.model_dump()
    if not scope.payroll:
        data.pop("base_salary")
    e = Employee(**data)
    db.add(e)
    db.flush()
    audit(db, scope, "employee_create", f"employee:{e.id}")
    db.commit()
    return _emp_row(e, scope)


@router.patch("/employees/{emp_id}")
def update_employee(emp_id: int, body: dict, scope: Scope = Depends(require("hr.write")), db: Session = Depends(get_db)):
    e = db.get(Employee, emp_id)
    if not e or not scope.allows_branch(e.branch_id):
        raise HTTPException(404, "Not found")
    allowed = {"full_name", "phone", "branch_id", "position_id", "hire_date", "status", "pay_type", "schedule_code",
               "leave_balance_days", "telegram_id"} | ({"base_salary"} if scope.payroll else set())
    for k, v in body.items():
        if k in allowed:
            if k == "branch_id" and not scope.allows_branch(v):
                raise HTTPException(403, "Not your branch")
            if k == "hire_date" and v:
                v = date.fromisoformat(v)
            setattr(e, k, v)
    audit(db, scope, "employee_update", f"employee:{e.id}", fields=list(body))
    db.commit()
    return _emp_row(e, scope)


class FireIn(BaseModel):
    reason: str = Field(min_length=3)
    fire_date: date | None = None


@router.post("/employees/{emp_id}/fire")
def fire_employee(emp_id: int, body: FireIn, scope: Scope = Depends(require("hr.write")), db: Session = Depends(get_db)):
    """A person fires. The record is kept (status=fired) for turnover analytics."""
    e = db.get(Employee, emp_id)
    if not e or not scope.allows_branch(e.branch_id):
        raise HTTPException(404, "Not found")
    e.status, e.fire_date, e.fire_reason = "fired", body.fire_date or date.today(), body.reason
    audit(db, scope, "employee_fire", f"employee:{e.id}", reason=body.reason)
    db.commit()
    return _emp_row(e, scope)


@router.get("/employees/{emp_id}")
def employee_detail(emp_id: int, scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    e = db.get(Employee, emp_id)
    if not e:
        raise HTTPException(404, "Not found")
    card = _guard(people.employee_card, db, scope, e)
    plan = db.scalar(select(OnboardingPlan).where(OnboardingPlan.employee_id == e.id))
    card["onboarding"] = onboarding.plan_card(plan) if plan else None
    card["documents"] = people.my_documents(db, e)
    card["requests"] = people.list_requests(db, scope, employee_id=e.id)[:10]
    return card


# ---------------- attendance & tabel ----------------

@router.get("/attendance/day")
def attendance_day(day: date | None = None, branch_id: int | None = None, scope: Scope = Depends(require("hr.read")),
                   db: Session = Depends(get_db)):
    return attendance.day_summary(db, scope, day or date.today(), branch_id)


@router.get("/tabel")
def tabel(month: str | None = None, branch_id: int | None = None, scope: Scope = Depends(require("hr.read")),
          db: Session = Depends(get_db)):
    t = attendance.month_tabel(db, scope, _month(month), branch_id)
    p = payroll.period(db, _month(month))
    t["closed"] = p.tabel_closed
    db.commit()
    return t


@router.get("/tabel/excel")
def tabel_excel(month: str | None = None, branch_id: int | None = None, scope: Scope = Depends(require("hr.read")),
                db: Session = Depends(get_db)):
    data = reports.tabel_excel(db, scope, _month(month), branch_id)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="tabel-{_month(month)}.xlsx"'})


class OverrideIn(BaseModel):
    employee_id: int
    day: date
    check_in: datetime | None = None
    check_out: datetime | None = None
    reason: str = Field(min_length=3)


@router.post("/tabel/override")
def tabel_override(body: OverrideIn, scope: Scope = Depends(require("attendance.write")), db: Session = Depends(get_db)):
    e = db.get(Employee, body.employee_id)
    if not e or not scope.allows_branch(e.branch_id):
        raise HTTPException(404, "Not found")
    month = body.day.strftime("%Y-%m")
    if payroll.is_locked(db, month):
        raise HTTPException(409, "Month is closed — reopen the tabel first")
    db.add(HrOverride(**body.model_dump(), author=scope.actor))
    payroll.mark_changed(db, month)
    audit(db, scope, "tabel_override", f"employee:{e.id}", day=str(body.day), reason=body.reason)
    db.commit()
    return {"ok": True}


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3)


@router.post("/tabel/{month}/close")
def tabel_close(month: str, body: ReasonIn, scope: Scope = Depends(require("attendance.write")), db: Session = Depends(get_db)):
    if not scope.all_branches:
        raise HTTPException(403, "Only users without branch restriction close the tabel")
    p = payroll.period(db, month)
    p.tabel_closed = True
    audit(db, scope, "tabel_close", month, reason=body.reason)
    db.commit()
    return {"month": month, "closed": True}


@router.post("/tabel/{month}/reopen")
def tabel_reopen(month: str, body: ReasonIn, scope: Scope = Depends(require("attendance.write")), db: Session = Depends(get_db)):
    if not scope.all_branches:
        raise HTTPException(403, "Only users without branch restriction reopen the tabel")
    p = payroll.period(db, month)
    if p.payroll_status in ("approved", "paid", "closed"):
        raise HTTPException(409, "Payroll already approved")
    p.tabel_closed = False
    audit(db, scope, "tabel_reopen", month, reason=body.reason)
    db.commit()
    return {"month": month, "closed": False}


# ---------------- payroll ----------------

@router.get("/payroll")
def payroll_get(month: str | None = None, branch_id: int | None = None, scope: Scope = Depends(require("hr.read")),
                db: Session = Depends(get_db)):
    return payroll.payroll_table(db, scope, _month(month), branch_id)


@router.get("/payroll/{month}/precheck")
def payroll_precheck(month: str, scope: Scope = Depends(require("payroll.read")), db: Session = Depends(get_db)):
    return payroll.precheck(db, scope, month)


@router.post("/payroll/{month}/calculate")
def payroll_calculate(month: str, scope: Scope = Depends(require("payroll.write")), db: Session = Depends(get_db)):
    p = payroll.period(db, month)
    if p.payroll_status in ("approved", "paid", "closed"):
        raise HTTPException(409, f"Month is {p.payroll_status}")
    p.payroll_status, p.calculated_at, p.changed_after_calc = "calculated", datetime.now(), False
    audit(db, scope, "payroll_calculate", month)
    db.commit()
    return payroll.payroll_table(db, scope, month)


class StatusIn(BaseModel):
    status: str
    reason: str = Field(min_length=3)


@router.post("/payroll/{month}/status")
def payroll_status(month: str, body: StatusIn, scope: Scope = Depends(require("payroll.approve")), db: Session = Depends(get_db)):
    """Human only: calculated -> approved -> paid -> closed."""
    if not scope.all_branches:
        raise HTTPException(403, "Only users without branch restriction approve payroll")
    p = payroll.period(db, month)
    flow = {"calculated": "approved", "approved": "paid", "paid": "closed"}
    if flow.get(p.payroll_status) != body.status:
        raise HTTPException(409, f"Cannot go from {p.payroll_status} to {body.status}")
    if body.status == "approved" and p.changed_after_calc:
        raise HTTPException(409, "Data changed after calculation — recalculate first")
    p.payroll_status = body.status
    if body.status == "approved":
        p.approved_by, p.approve_reason = scope.actor, body.reason
    audit(db, scope, f"payroll_{body.status}", month, reason=body.reason)
    db.commit()
    return {"month": month, "status": p.payroll_status}


class EntryIn(BaseModel):
    employee_id: int
    month: str
    kind: str
    amount: int = 0
    reason: str = Field(min_length=3, max_length=300)


@router.post("/payroll/entries")
def payroll_entry(body: EntryIn, scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    if not (scope.can("payroll.write") or scope.can("hr.write")):
        raise HTTPException(403, "No right to add entries")
    if body.kind not in {"advance", "bonus", "penalty", "other", "warning", "kpi"}:
        raise HTTPException(400, "Bad kind")
    if not 0 <= body.amount <= 100_000_000:
        raise HTTPException(400, "Amount out of range")
    e = db.get(Employee, body.employee_id)
    if not e or not scope.allows_branch(e.branch_id):
        raise HTTPException(404, "Not found")
    if payroll.is_locked(db, body.month) and body.kind != "warning":
        raise HTTPException(409, "Month is approved/closed — money entries are blocked")
    db.add(PayrollEntry(**body.model_dump(), author=scope.actor))
    payroll.mark_changed(db, body.month)
    audit(db, scope, "payroll_entry", f"employee:{e.id}", kind=body.kind, amount=body.amount, reason=body.reason)
    db.commit()
    return {"ok": True}


@router.get("/payroll/entries")
def payroll_entries(month: str | None = None, employee_id: int | None = None, scope: Scope = Depends(require("hr.read")),
                    db: Session = Depends(get_db)):
    q = select(PayrollEntry).join(Employee, Employee.id == PayrollEntry.employee_id).where(PayrollEntry.month == _month(month))
    if scope.branch_ids is not None:
        q = q.where(Employee.branch_id.in_(scope.branch_ids or {-1}))
    if employee_id:
        q = q.where(PayrollEntry.employee_id == employee_id)
    return [{"id": x.id, "employee_id": x.employee_id, "kind": x.kind,
             "amount": x.amount if scope.payroll or x.kind == "warning" else None, "reason": x.reason,
             "author": x.author, "created_at": x.created_at, "cancelled": x.cancelled, "cancel_reason": x.cancel_reason}
            for x in db.scalars(q.order_by(PayrollEntry.id.desc()))]


@router.post("/payroll/entries/{entry_id}/cancel")
def payroll_entry_cancel(entry_id: int, body: ReasonIn, scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    x = db.get(PayrollEntry, entry_id)
    if not x or x.cancelled:
        raise HTTPException(404, "Not found")
    if not (scope.can("payroll.write") or scope.can("hr.write")):
        raise HTTPException(403, "No right")
    if payroll.is_locked(db, x.month):
        raise HTTPException(409, "Month is locked")
    x.cancelled, x.cancel_reason = True, body.reason  # never deleted
    payroll.mark_changed(db, x.month)
    audit(db, scope, "payroll_entry_cancel", f"entry:{x.id}", reason=body.reason)
    db.commit()
    return {"ok": True}


@router.post("/payroll/sales/import")
async def sales_import(month: str, file: UploadFile, scope: Scope = Depends(require("payroll.write")), db: Session = Depends(get_db)):
    """CSV: employee_id,amount  (or phone,amount). Sales % bonus is calculated from this."""
    text = (await file.read()).decode("utf-8-sig")
    ok, missing = 0, []
    for row in csv.DictReader(io.StringIO(text)):
        emp = None
        if row.get("employee_id"):
            emp = db.get(Employee, int(row["employee_id"]))
        elif row.get("phone"):
            emp = db.scalar(select(Employee).where(Employee.phone == row["phone"].strip()))
        if not emp:
            missing.append(row)
            continue
        rec = db.scalar(select(SalesRecord).where(SalesRecord.employee_id == emp.id, SalesRecord.month == month))
        if rec:
            rec.amount = int(float(row["amount"]))
        else:
            db.add(SalesRecord(employee_id=emp.id, month=month, amount=int(float(row["amount"]))))
        ok += 1
    payroll.mark_changed(db, month)
    audit(db, scope, "sales_import", month, rows=ok, missing=len(missing))
    db.commit()
    return {"imported": ok, "not_found": missing[:20]}


# ---------------- requests & approvals ----------------

@router.get("/requests")
def requests_list(status: str | None = None, scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    return people.list_requests(db, scope, status)


class DecideIn(BaseModel):
    approve: bool
    reason: str = Field(min_length=3)


@router.post("/requests/{rid}/decide")
def requests_decide(rid: int, body: DecideIn, scope: Scope = Depends(require("requests.decide")), db: Session = Depends(get_db)):
    r = _guard(people.decide_request, db, scope, rid, body.approve, body.reason)
    db.commit()
    return {"id": r.id, "status": r.status}


@router.get("/approvals")
def approvals(status: str = "pending", scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    q = select(ApprovalRequest).where(ApprovalRequest.status == status).order_by(ApprovalRequest.created_at.desc())
    return [{"id": a.id, "action": a.action, "summary": a.summary, "requested_by": a.requested_by, "status": a.status,
             "created_at": a.created_at, "decided_by": a.decided_by, "decision_reason": a.decision_reason}
            for a in db.scalars(q) if a.branch_id is None or scope.allows_branch(a.branch_id)]


@router.post("/approvals/{aid}/decide")
def approvals_decide(aid: int, body: DecideIn, scope: Scope = Depends(require("hr.write")), db: Session = Depends(get_db)):
    a = _guard(people.decide_approval, db, scope, aid, body.approve, body.reason)
    db.commit()
    return {"id": a.id, "status": a.status}


# ---------------- onboarding / documents / SOP ----------------

@router.get("/onboarding")
def onboarding_list(scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    return onboarding.status(db, scope)


class OnbIn(BaseModel):
    employee_id: int
    mentor: str | None = None
    start_date: date | None = None


@router.post("/onboarding")
def onboarding_create(body: OnbIn, scope: Scope = Depends(require("onboarding")), db: Session = Depends(get_db)):
    e = db.get(Employee, body.employee_id)
    if not e or not scope.allows_branch(e.branch_id):
        raise HTTPException(404, "Not found")
    plan = _guard(onboarding.create_plan, db, scope, e, body.mentor, body.start_date)
    db.commit()
    return onboarding.plan_card(plan)


@router.post("/onboarding/items/{item_id}")
def onboarding_item(item_id: int, done: bool = True, scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    i = _guard(onboarding.mark_item, db, scope, item_id, done)
    db.commit()
    return {"id": i.id, "done": i.done}


class ScoreIn(BaseModel):
    score: int = Field(ge=0, le=100)
    stage: int | None = None


@router.post("/onboarding/{plan_id}/score")
def onboarding_score(plan_id: int, body: ScoreIn, scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    p = db.get(OnboardingPlan, plan_id)
    if not p:
        raise HTTPException(404, "Not found")
    r = _guard(onboarding.record_score, db, scope, p, body.score, body.stage)
    db.commit()
    return r


@router.get("/documents/expiring")
def documents_expiring(days: int = 60, scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    return people.expiring_documents(db, scope, days)


class DocIn(BaseModel):
    employee_id: int
    doc_type: str
    number: str | None = None
    issued: date | None = None
    expires: date | None = None


@router.post("/documents")
def documents_create(body: DocIn, scope: Scope = Depends(require("hr.write")), db: Session = Depends(get_db)):
    e = db.get(Employee, body.employee_id)
    if not e or not scope.allows_branch(e.branch_id):
        raise HTTPException(404, "Not found")
    db.add(Document(**body.model_dump()))
    audit(db, scope, "document_add", f"employee:{e.id}", doc_type=body.doc_type)
    db.commit()
    return {"ok": True}


@router.get("/sops")
def sops(q: str = "", position_code: str | None = None, scope: Scope = Depends(panel_scope), db: Session = Depends(get_db)):
    return people.find_sops(db, q, position_code, limit=100)


@router.post("/sops/upload")
async def sops_upload(file: UploadFile, position_code: str | None = None, tags: str = "",
                      scope: Scope = Depends(require("hr.write")), db: Session = Depends(get_db)):
    """Upload .md / .txt. A markdown file with several '# Title' sections becomes several SOPs."""
    text = (await file.read()).decode("utf-8-sig")
    chunks, title, buf = [], (file.filename or "SOP").rsplit(".", 1)[0], []
    for line in text.splitlines():
        if line.startswith("# "):
            if buf and "".join(buf).strip():
                chunks.append((title, "\n".join(buf).strip()))
            title, buf = line[2:].strip(), []
        else:
            buf.append(line)
    if "".join(buf).strip():
        chunks.append((title, "\n".join(buf).strip()))
    for t, body in chunks:
        db.add(Sop(title=t, body=body, position_code=position_code or None, tags=tags))
    audit(db, scope, "sop_upload", file.filename, count=len(chunks))
    db.commit()
    return {"created": len(chunks)}


# ---------------- recruiting ----------------

@router.get("/vacancies")
def vacancies(scope: Scope = Depends(require("recruiting.read")), db: Session = Depends(get_db)):
    rows = []
    sla = {v["id"]: v for v in analytics.vacancies_sla(db, scope)}
    for v in db.scalars(select(Vacancy).order_by(Vacancy.id.desc())):
        if v.branch_id and not scope.allows_branch(v.branch_id):
            continue
        rows.append({"id": v.id, "title": v.title, "branch": v.branch.name if v.branch else None, "branch_id": v.branch_id,
                     "status": v.status, "salary_text": v.salary_text, "schedule_text": v.schedule_text,
                     "opened_at": v.opened_at, "sla_days": v.sla_days, "light": sla.get(v.id, {}).get("light"),
                     "days_open": sla.get(v.id, {}).get("days_open"), "ad_text": v.ad_text or recruiting.render_ad(v)})
    return rows


class VacancyIn(BaseModel):
    title: str
    branch_id: int | None = None
    position_code: str | None = None
    salary_text: str | None = None
    schedule_text: str | None = None
    requirements: str = ""


@router.post("/vacancies")
def vacancy_create(body: VacancyIn, scope: Scope = Depends(require("recruiting")), db: Session = Depends(get_db)):
    v = Vacancy(**body.model_dump())
    db.add(v)
    db.flush()
    audit(db, scope, "vacancy_draft", f"vacancy:{v.id}")
    db.commit()
    return {"id": v.id, "missing": recruiting.missing_fields({"title": v.title, "branch": v.branch_id,
                                                              "salary_text": v.salary_text, "schedule_text": v.schedule_text}),
            "preview": recruiting.render_ad(v)}


@router.post("/vacancies/{vid}/open")
def vacancy_open(vid: int, scope: Scope = Depends(require("recruiting")), db: Session = Depends(get_db)):
    v = db.get(Vacancy, vid)
    if not v:
        raise HTTPException(404, "Not found")
    _guard(recruiting.open_vacancy, db, scope, v)
    db.commit()
    return {"id": v.id, "status": v.status, "ad_text": v.ad_text}


@router.get("/candidates")
def candidates(vacancy_id: int | None = None, scope: Scope = Depends(require("recruiting.read")), db: Session = Depends(get_db)):
    q = select(Candidate).order_by(Candidate.created_at.desc())
    if vacancy_id:
        q = q.where(Candidate.vacancy_id == vacancy_id)
    out = []
    for c in db.scalars(q):
        if c.vacancy and c.vacancy.branch_id and not scope.allows_branch(c.vacancy.branch_id):
            continue
        out.append({"id": c.id, "full_name": c.full_name, "phone": c.phone, "vacancy": c.vacancy.title if c.vacancy else None,
                    "score": c.score, "label": c.label, "status": c.status, "breakdown": c.breakdown,
                    "answers": c.answers, "source": c.source, "created_at": c.created_at})
    return out


class CandStatusIn(BaseModel):
    status: str


@router.post("/candidates/{cid}/status")
def candidate_status(cid: int, body: CandStatusIn, scope: Scope = Depends(require("recruiting")), db: Session = Depends(get_db)):
    c = db.get(Candidate, cid)
    if not c:
        raise HTTPException(404, "Not found")
    _guard(recruiting.set_status, db, scope, c, body.status)
    db.commit()
    return {"id": c.id, "status": c.status}


# ---------------- branch leads (pharmacy heads / regional managers) ----------------

@router.get("/branch-leads")
def branch_leads(scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    rows = []
    for bl in db.scalars(select(BranchLead)):
        if not scope.allows_branch(bl.branch_id):
            continue
        e = db.get(Employee, bl.employee_id)
        rows.append({"id": bl.id, "branch_id": bl.branch_id, "employee_id": e.id, "full_name": e.full_name,
                     "telegram_linked": e.telegram_id is not None})
    return rows


class LeadIn(BaseModel):
    branch_id: int
    employee_id: int


@router.post("/branch-leads")
def branch_lead_add(body: LeadIn, scope: Scope = Depends(require("hr.write")), db: Session = Depends(get_db)):
    if not scope.all_branches:
        raise HTTPException(403, "Only users without branch restriction assign leads")
    if not db.scalar(select(BranchLead).where(BranchLead.branch_id == body.branch_id, BranchLead.employee_id == body.employee_id)):
        db.add(BranchLead(**body.model_dump()))
    audit(db, scope, "branch_lead_add", f"branch:{body.branch_id}", employee_id=body.employee_id)
    db.commit()
    return {"ok": True}


@router.delete("/branch-leads/{lid}")
def branch_lead_remove(lid: int, scope: Scope = Depends(require("hr.write")), db: Session = Depends(get_db)):
    if not scope.all_branches:
        raise HTTPException(403, "Only users without branch restriction remove leads")
    bl = db.get(BranchLead, lid)
    if bl:
        audit(db, scope, "branch_lead_remove", f"branch:{bl.branch_id}", employee_id=bl.employee_id)
        db.delete(bl)
        db.commit()
    return {"ok": True}


# ---------------- analytics, chats, audit, users ----------------

@router.get("/analytics")
def analytics_all(months: int = 3, scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    return {"headcount_branch": analytics.headcount(db, scope, "branch"),
            "headcount_position": analytics.headcount(db, scope, "position"),
            "turnover": analytics.turnover(db, scope, months, "branch"),
            "turnover_region": analytics.turnover(db, scope, months, "region"),
            "attendance_30d": attendance.attendance_rate(db, scope, 30)}


@router.get("/chats")
def chats(agent: str | None = None, q: str = "", scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    stmt = select(ChatMessage).order_by(ChatMessage.id.desc()).limit(300)
    if agent:
        stmt = stmt.where(ChatMessage.agent == agent)
    rows = [m for m in db.scalars(stmt) if (scope.branch_ids is None or m.branch_id in scope.branch_ids)
            and (not q or q.lower() in m.text.lower())]
    return [{"id": m.id, "agent": m.agent, "user_key": m.user_key, "role": m.role, "text": m.text, "ts": m.ts} for m in rows]


@router.get("/audit")
def audit_log(limit: int = 200, scope: Scope = Depends(require("audit.read")), db: Session = Depends(get_db)):
    if not scope.all_branches:
        raise HTTPException(403, "Only users without branch restriction see audit")
    return [{"id": a.id, "ts": a.ts, "actor": a.actor, "role": a.actor_role, "action": a.action, "target": a.target,
             "details": a.details} for a in db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 1000)))]


@router.get("/users")
def users(scope: Scope = Depends(require("*")), db: Session = Depends(get_db)):
    return [{"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role, "branch_scope": u.branch_scope,
             "can_see_payroll": u.can_see_payroll, "active": u.active} for u in db.scalars(select(User))]
