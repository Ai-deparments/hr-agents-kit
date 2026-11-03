"""Company structure and access: roles builder, users, departments, dictionaries, bot registrations, broadcasts."""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import hash_password, require
from ..db import get_db
from ..models import Branch, Department, Employee, Outbox, Position, Region, Registration, Role, User
from ..config import cfg, settings
from ..models import PanelInvite
from ..rbac import BOT_FUNCTIONS, PERMISSIONS, Scope, audit
from ..services import panel_access as pa

router = APIRouter(prefix="/api")
ADMIN = require("*")  # main admin (and CEO): roles, users, departments


def _code(s: str) -> str:
    c = re.sub(r"[^a-z0-9_]+", "_", s.lower()).strip("_")[:40]
    if not c:
        raise HTTPException(400, "Bad code")
    return c


# ---------------- bot: who sees what in the HR group and in private chat ----------------

@router.get("/bot-visibility")
def bot_visibility(scope: Scope = Depends(ADMIN), db: Session = Depends(get_db)):
    from ..services import visibility
    return {"categories": visibility.CATEGORIES, "channels": list(visibility.CHANNELS), "roles": list(visibility.ROLES),
            "people": visibility.people_with_bot_access(db), "settings": visibility.get(db)}


@router.put("/bot-visibility")
def bot_visibility_save(body: dict, scope: Scope = Depends(ADMIN), db: Session = Depends(get_db)):
    from ..services import visibility
    v = visibility.save(db, body)
    audit(db, scope, "bot_visibility", None, roles=v["roles"], people=sorted(v["people"]))
    db.commit()
    return v


# ---------------- permission catalog ----------------

@router.get("/org/catalog")
def catalog(scope: Scope = Depends(require("hr.read"))):
    return {"permissions": [{"code": k, **v} for k, v in PERMISSIONS.items()],
            "bot_functions": [{"code": k, **v} for k, v in BOT_FUNCTIONS.items()]}


# ---------------- roles ----------------

class RoleIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str | None = None
    description: str = Field(default="", max_length=500)
    perms: list[str] = []


def _clean_perms(perms: list[str]) -> list[str]:
    bad = [p for p in perms if p not in PERMISSIONS]
    if bad:
        raise HTTPException(400, f"Unknown permission: {', '.join(bad)}")
    return sorted(set(perms))


def _role_row(r: Role, users: int) -> dict:
    return {"id": r.id, "code": r.code, "name": r.name, "description": r.description, "perms": r.perms,
            "system": r.system, "users": users}


@router.get("/roles")
def roles(scope: Scope = Depends(ADMIN), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())
    return [_role_row(r, counts.get(r.code, 0)) for r in db.scalars(select(Role).order_by(Role.system.desc(), Role.name))]


@router.post("/roles")
def role_create(body: RoleIn, scope: Scope = Depends(ADMIN), db: Session = Depends(get_db)):
    code = _code(body.code or body.name)
    if db.scalar(select(Role).where(Role.code == code)):
        raise HTTPException(409, "Role with this code exists")
    r = Role(code=code, name=body.name, description=body.description, perms=_clean_perms(body.perms))
    db.add(r)
    db.flush()
    audit(db, scope, "role_create", f"role:{code}", perms=r.perms)
    db.commit()
    return _role_row(r, 0)


@router.patch("/roles/{rid}")
def role_update(rid: int, body: RoleIn, scope: Scope = Depends(ADMIN), db: Session = Depends(get_db)):
    r = db.get(Role, rid)
    if not r:
        raise HTTPException(404, "Not found")
    if "*" in r.perms:
        raise HTTPException(409, "Full-access roles are fixed")
    r.name, r.description, r.perms = body.name, body.description, _clean_perms(body.perms)
    audit(db, scope, "role_update", f"role:{r.code}", perms=r.perms)
    db.commit()
    return _role_row(r, db.scalar(select(func.count()).where(User.role == r.code)) or 0)


@router.delete("/roles/{rid}")
def role_delete(rid: int, scope: Scope = Depends(ADMIN), db: Session = Depends(get_db)):
    r = db.get(Role, rid)
    if not r:
        raise HTTPException(404, "Not found")
    if r.system:
        raise HTTPException(409, "Built-in roles cannot be deleted")
    if db.scalar(select(User.id).where(User.role == r.code)):
        raise HTTPException(409, "Role is assigned to users — move them first")
    audit(db, scope, "role_delete", f"role:{r.code}")
    db.delete(r)
    db.commit()
    return {"ok": True}


# ---------------- panel users ----------------

class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=60, pattern=r"^[a-zA-Z0-9_.-]+$")
    full_name: str = ""
    password: str = Field(min_length=10)
    role: str
    branch_scope: list[int] | None = None
    can_see_payroll: bool = False


class UserPatch(BaseModel):
    full_name: str | None = None
    role: str | None = None
    branch_scope: list[int] | None = None
    can_see_payroll: bool | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=10)


_user_row = pa.user_row


def _role_exists(db: Session, code: str) -> None:
    if not db.scalar(select(Role.id).where(Role.code == code)):
        raise HTTPException(400, "Unknown role")


def _pa(fn, *a, **kw):
    """Run a panel_access call; its AccessError becomes a 400/404/409 for the panel."""
    try:
        return fn(*a, **kw)
    except pa.AccessError as e:
        msg = str(e)
        raise HTTPException(409 if "taken" in msg or "cannot" in msg else 404 if "Nothing" in msg or "not found" in msg
                            else 400, msg)


@router.get("/users")
def users(scope: Scope = Depends(ADMIN), db: Session = Depends(get_db)):
    return [_user_row(u) for u in db.scalars(select(User).order_by(User.username))]


@router.post("/users")
def user_create(body: UserIn, scope: Scope = Depends(ADMIN), db: Session = Depends(get_db)):
    _role_exists(db, body.role)
    if db.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(409, "Username taken")
    u = User(username=body.username, full_name=body.full_name, password_hash=hash_password(body.password), role=body.role,
             branch_scope=body.branch_scope, can_see_payroll=body.can_see_payroll)
    db.add(u)
    db.flush()
    audit(db, scope, "user_create", f"user:{u.username}", role=u.role)
    db.commit()
    return _user_row(u)


@router.patch("/users/{uid}")
def user_update(uid: int, body: UserPatch, scope: Scope = Depends(ADMIN), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Not found")
    data = body.model_dump(exclude_unset=True)
    if u.username == "admin" and (data.get("active") is False or data.get("role") not in (None, "admin")):
        raise HTTPException(409, "The main admin cannot be disabled or demoted")
    if "role" in data:
        _role_exists(db, data["role"])
    if pw := data.pop("password", None):
        u.password_hash = hash_password(pw)
    for k, v in data.items():
        setattr(u, k, v)
    audit(db, scope, "user_update", f"user:{u.username}", fields=sorted(body.model_dump(exclude_unset=True)))
    db.commit()
    return _user_row(u)


# ---------------- departments (main admin only) ----------------

class DeptIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=300)


@router.get("/departments")
def departments(scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Employee.department_id, func.count()).where(Employee.status != "fired")
                             .group_by(Employee.department_id)).all())
    return [{"id": d.id, "name": d.name, "description": d.description, "headcount": counts.get(d.id, 0)}
            for d in db.scalars(select(Department).order_by(Department.name))]


@router.post("/departments")
def department_create(body: DeptIn, scope: Scope = Depends(ADMIN), db: Session = Depends(get_db)):
    if db.scalar(select(Department.id).where(Department.name == body.name)):
        raise HTTPException(409, "Department exists")
    d = Department(**body.model_dump())
    db.add(d)
    db.flush()
    audit(db, scope, "department_create", f"department:{d.id}", name=d.name)
    db.commit()
    return {"id": d.id, "name": d.name, "description": d.description, "headcount": 0}


@router.patch("/departments/{did}")
def department_update(did: int, body: DeptIn, scope: Scope = Depends(ADMIN), db: Session = Depends(get_db)):
    d = db.get(Department, did)
    if not d:
        raise HTTPException(404, "Not found")
    d.name, d.description = body.name, body.description
    audit(db, scope, "department_update", f"department:{d.id}")
    db.commit()
    return {"id": d.id, "name": d.name, "description": d.description}


@router.delete("/departments/{did}")
def department_delete(did: int, scope: Scope = Depends(ADMIN), db: Session = Depends(get_db)):
    d = db.get(Department, did)
    if not d:
        raise HTTPException(404, "Not found")
    if db.scalar(select(Employee.id).where(Employee.department_id == did)):
        raise HTTPException(409, "Department has employees — move them first")
    audit(db, scope, "department_delete", f"department:{d.id}", name=d.name)
    db.delete(d)
    db.commit()
    return {"ok": True}


# ---------------- dictionaries: positions, regions, branches ----------------

class PositionIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    code: str | None = None
    is_manager: bool = False


class RegionIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str | None = None


class BranchIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: str | None = None
    region_id: int | None = None
    city: str | None = None
    mode: str = Field(default="day", pattern=r"^(day|24/7)$")


def _unique_code(db: Session, model, raw: str, limit: int) -> str:
    base = _code(raw)[:limit]
    code, i = base, 1
    while db.scalar(select(model.id).where(model.code == code)):
        i += 1
        code = f"{base[:limit - 3]}_{i}"
    return code


@router.post("/positions")
def position_create(body: PositionIn, scope: Scope = Depends(require("hr.write")), db: Session = Depends(get_db)):
    p = Position(code=_unique_code(db, Position, body.code or body.title, 40), title=body.title, is_manager=body.is_manager)
    db.add(p)
    db.flush()
    audit(db, scope, "position_create", f"position:{p.code}")
    db.commit()
    return {"id": p.id, "code": p.code, "title": p.title}


@router.post("/regions")
def region_create(body: RegionIn, scope: Scope = Depends(require("hr.write")), db: Session = Depends(get_db)):
    r = Region(code=_unique_code(db, Region, body.code or body.name, 20), name=body.name)
    db.add(r)
    db.flush()
    audit(db, scope, "region_create", f"region:{r.code}")
    db.commit()
    return {"id": r.id, "code": r.code, "name": r.name}


@router.post("/branches")
def branch_create(body: BranchIn, scope: Scope = Depends(require("hr.write")), db: Session = Depends(get_db)):
    if not scope.all_branches:
        raise HTTPException(403, "Only users without branch restriction add branches")
    b = Branch(code=_unique_code(db, Branch, body.code or body.name, 20), name=body.name, region_id=body.region_id,
               city=body.city, mode=body.mode)
    db.add(b)
    db.flush()
    audit(db, scope, "branch_create", f"branch:{b.code}")
    db.commit()
    return {"id": b.id, "code": b.code, "name": b.name}


# ---------------- registrations from the bot ("I am an employee") ----------------

def _reg_row(r: Registration) -> dict:
    return {"id": r.id, "telegram_id": r.telegram_id, "tg_username": r.tg_username, "full_name": r.full_name,
            "position_text": r.position_text, "region_text": r.region_text, "status": r.status,
            "employee_id": r.employee_id, "functions": r.functions, "decided_by": r.decided_by,
            "decision_reason": r.decision_reason, "created_at": r.created_at, "decided_at": r.decided_at,
            "source": r.source or "form", "bots": r.bots or [], "last_at": r.last_at or r.created_at, "requests": r.requests or 1}


@router.get("/registrations")
def registrations(status: str | None = "pending", scope: Scope = Depends(require("registrations")), db: Session = Depends(get_db)):
    q = select(Registration).order_by(Registration.id.desc())
    if status:
        q = q.where(Registration.status == status)
    return [_reg_row(r) for r in db.scalars(q.limit(500))]


class ApproveIn(BaseModel):
    functions: list[str] = []
    employee_id: int | None = None  # link to an existing card, or create a new one from the fields below
    branch_id: int | None = None
    department_id: int | None = None
    position_id: int | None = None


def _clean_functions(fns: list[str]) -> list[str]:
    bad = [f for f in fns if f not in BOT_FUNCTIONS]
    if bad:
        raise HTTPException(400, f"Unknown function: {', '.join(bad)}")
    return sorted(set(fns))


def _notify(db: Session, tg_id: int, text: str) -> None:
    db.add(Outbox(telegram_id=tg_id, text=text))


def _fn_list(fns: list[str]) -> str:
    return "\n".join(f"• {BOT_FUNCTIONS[f]['uz']} / {BOT_FUNCTIONS[f]['ru']}" for f in fns) or "—"


@router.post("/registrations/{rid}/approve")
def registration_approve(rid: int, body: ApproveIn, scope: Scope = Depends(require("registrations")), db: Session = Depends(get_db)):
    r = db.get(Registration, rid)
    if not r or r.status != "pending":
        raise HTTPException(404, "Not found or already decided")
    fns = _clean_functions(body.functions)
    if body.department_id and not db.get(Department, body.department_id):
        raise HTTPException(400, "Unknown department")
    if body.position_id and not db.get(Position, body.position_id):
        raise HTTPException(400, "Unknown position")
    if db.scalar(select(Employee).where(Employee.telegram_id == r.telegram_id, Employee.id != (body.employee_id or -1))):
        raise HTTPException(409, "This Telegram account is already linked to another employee")
    if body.employee_id:
        e = db.get(Employee, body.employee_id)
        if not e or not scope.allows_branch(e.branch_id):
            raise HTTPException(404, "Employee not found")
        if e.telegram_id and e.telegram_id != r.telegram_id:
            raise HTTPException(409, "Employee is linked to another Telegram account")
    else:
        if not body.branch_id or not scope.allows_branch(body.branch_id):
            raise HTTPException(400, "Choose a branch you manage")
        e = Employee(full_name=r.full_name, branch_id=body.branch_id, status="probation")
        db.add(e)
    e.telegram_id = r.telegram_id
    e.bot_functions = fns
    if body.department_id:
        e.department_id = body.department_id
    if body.position_id:
        e.position_id = body.position_id
    db.flush()
    r.status, r.employee_id, r.functions = "approved", e.id, fns
    r.decided_by, r.decided_at = scope.actor, datetime.now()
    _notify(db, r.telegram_id, "✅ Arizangiz qabul qilindi! Sizga ochilgan funksiyalar:\n"
                               "✅ Ваша заявка принята! Вам открыты функции:\n\n" + _fn_list(fns) + "\n\n/start")
    audit(db, scope, "registration_approve", f"registration:{r.id}", employee_id=e.id, functions=fns)
    from ..services import onboarding_media
    onboarding_media.auto_assign(db, scope, e)  # newcomer gets the course for their position right away
    onboarding_media.deliver_due(db)
    db.commit()
    return _reg_row(r)


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@router.post("/registrations/{rid}/reject")
def registration_reject(rid: int, body: RejectIn, scope: Scope = Depends(require("registrations")), db: Session = Depends(get_db)):
    r = db.get(Registration, rid)
    if not r or r.status != "pending":
        raise HTTPException(404, "Not found or already decided")
    r.status, r.decided_by, r.decision_reason, r.decided_at = "rejected", scope.actor, body.reason, datetime.now()
    if (r.source or "form") == "form":  # strangers (access requests) get silence, not a message
        _notify(db, r.telegram_id, "Arizangiz rad etildi.\nSabab: " + body.reason)
    audit(db, scope, "registration_reject", f"registration:{r.id}", reason=body.reason)
    db.commit()
    return _reg_row(r)


class FunctionsIn(BaseModel):
    functions: list[str]


@router.post("/employees/{emp_id}/functions")
def employee_functions(emp_id: int, body: FunctionsIn, scope: Scope = Depends(require("registrations")),
                       db: Session = Depends(get_db)):
    e = db.get(Employee, emp_id)
    if not e or not scope.allows_branch(e.branch_id):
        raise HTTPException(404, "Not found")
    e.bot_functions = _clean_functions(body.functions)
    if e.telegram_id:
        _notify(db, e.telegram_id, "🔑 Bot funksiyalaringiz yangilandi / Ваши функции обновлены:\n\n" + _fn_list(e.bot_functions))
    audit(db, scope, "employee_functions", f"employee:{e.id}", functions=e.bot_functions)
    db.commit()
    return {"id": e.id, "functions": e.bot_functions}


# ---------------- broadcast to employees through the bot ----------------

class BroadcastIn(BaseModel):
    text: str = Field(min_length=3, max_length=3500)
    employee_ids: list[int] = []
    department_id: int | None = None
    branch_id: int | None = None


@router.post("/broadcast")
def broadcast(body: BroadcastIn, scope: Scope = Depends(require("broadcast")), db: Session = Depends(get_db)):
    """A person sends it (mass broadcast is human-only). Only linked, active employees in the sender's branches."""
    q = select(Employee).where(Employee.status != "fired", Employee.telegram_id.is_not(None))
    if body.employee_ids:
        q = q.where(Employee.id.in_(body.employee_ids))
    if body.department_id:
        q = q.where(Employee.department_id == body.department_id)
    if body.branch_id:
        q = q.where(Employee.branch_id == body.branch_id)
    if not (body.employee_ids or body.department_id or body.branch_id) and not scope.all_branches:
        raise HTTPException(400, "Choose recipients")
    targets = [e for e in db.scalars(q) if scope.allows_branch(e.branch_id)]
    for e in targets:
        _notify(db, e.telegram_id, body.text)
    audit(db, scope, "broadcast", None, recipients=len(targets), chars=len(body.text))
    db.commit()
    return {"queued": len(targets)}


@router.get("/outbox/stats")
def outbox_stats(scope: Scope = Depends(require("broadcast")), db: Session = Depends(get_db)):
    pending = db.scalar(select(func.count()).where(Outbox.sent_at.is_(None), Outbox.error.is_(None))) or 0
    failed = db.scalar(select(func.count()).where(Outbox.error.is_not(None))) or 0
    return {"pending": pending, "failed": failed}


@router.post("/registrations/reject-all")
def registrations_reject_all(body: RejectIn, scope: Scope = Depends(require("registrations")), db: Session = Depends(get_db)):
    """'Hammasini rad etish': every pending access request from strangers, silently."""
    n = 0
    for r in db.scalars(select(Registration).where(Registration.status == "pending", Registration.source == "access")):
        r.status, r.decided_by, r.decision_reason, r.decided_at = "rejected", scope.actor, body.reason, datetime.now()
        n += 1
    audit(db, scope, "registrations_reject_all", None, count=n, reason=body.reason)
    db.commit()
    return {"rejected": n}


# ---------------- who uses the agent bots ----------------

@router.get("/bot-access")
def bot_access(scope: Scope = Depends(require("registrations")), db: Session = Depends(get_db)):
    from ..models import ChatMessage
    last = dict(db.execute(select(ChatMessage.user_key, func.max(ChatMessage.ts)).where(ChatMessage.role == "user")
                           .group_by(ChatMessage.user_key)).all())
    rows = []
    for e in db.scalars(select(Employee).where(Employee.telegram_id.is_not(None)).order_by(Employee.full_name)):
        if not scope.allows_branch(e.branch_id):
            continue
        rows.append({"id": e.id, "full_name": e.full_name, "position": e.position.title if e.position else None,
                     "department": e.department.name if e.department else None, "telegram_id": e.telegram_id,
                     "functions": e.bot_functions or [], "status": e.status, "last_message": last.get(f"tg:{e.telegram_id}")})
    return rows


# ---------------- add a panel user via Telegram ----------------

class InviteIn(BaseModel):
    role: str
    branch_scope: list[int] | None = None
    can_see_payroll: bool = False


_invite_row = pa.invite_row


@router.post("/users/invite")
def user_invite(body: InviteIn, scope: Scope = Depends(ADMIN), db: Session = Depends(get_db)):
    out = _pa(pa.create_invite, db, scope, body.role, body.can_see_payroll, body.branch_scope)
    db.commit()
    return out


@router.get("/users/pending")
def users_pending(scope: Scope = Depends(ADMIN), db: Session = Depends(get_db)):
    out = pa.invites(db)
    db.commit()
    return out


class ApproveUserIn(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=60, pattern=r"^[a-zA-Z0-9_.-]+$")
    full_name: str | None = Field(default=None, max_length=160)


@router.post("/users/pending/{iid}/approve")
def users_pending_approve(iid: int, body: ApproveUserIn, scope: Scope = Depends(ADMIN), db: Session = Depends(get_db)):
    # the password goes only to the person's own Telegram chat, never back to the panel
    out = _pa(pa.approve_invite, db, scope, iid, body.username, body.full_name)
    db.commit()
    return out


@router.post("/users/pending/{iid}/reject")
def users_pending_reject(iid: int, scope: Scope = Depends(ADMIN), db: Session = Depends(get_db)):
    out = _pa(pa.reject_invite, db, scope, iid)
    db.commit()
    return out