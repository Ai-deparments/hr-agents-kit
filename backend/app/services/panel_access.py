"""Web-panel access: Telegram invites, logins, roles. Shared by the panel API and the HR agent's bot tools.
Passwords never come back to the caller: they go to the person's own Telegram chat through the Outbox."""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import hash_password
from ..config import cfg, settings
from ..models import Outbox, PanelInvite, Role, User
from ..rbac import PERMISSIONS, Scope, audit

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,60}$")


class AccessError(ValueError):
    """Bad input or state; the message is safe to show."""


def _notify(db: Session, tg_id: int, text: str) -> None:
    db.add(Outbox(telegram_id=tg_id, text=text))


def _tg_of(actor: str) -> int | None:
    return int(actor[3:]) if actor.startswith("tg:") and actor[3:].isdigit() else None


def role_exists(db: Session, code: str) -> None:
    if not db.scalar(select(Role.id).where(Role.code == code)):
        raise AccessError(f"Unknown role '{code}'")


def user_row(u: User) -> dict:
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role, "branch_scope": u.branch_scope,
            "can_see_payroll": u.can_see_payroll, "active": u.active, "telegram_id": u.telegram_id, "last_login": u.last_login}


def invite_row(i: PanelInvite) -> dict:
    return {"id": i.id, "role": i.role, "status": i.status, "tg_name": i.tg_name, "tg_username": i.tg_username,
            "telegram_id": i.telegram_id, "created_by": i.created_by, "created_at": i.created_at, "used_at": i.used_at,
            "expires_at": i.expires_at, "can_see_payroll": i.can_see_payroll, "branch_scope": i.branch_scope}


def _login_text(username: str, password: str) -> str:
    url = (settings().webapp_url or "").rstrip("/")
    return (f"✅ HR-panelga kirish ochildi / Доступ к HR-панели открыт.\n{url}\nLogin: {username}\nParol / Пароль: {password}\n"
            "Kirgandan keyin parolni almashtiring. / После входа смените пароль.")


def create_invite(db: Session, scope: Scope, role: str, can_see_payroll: bool = False,
                  branch_scope: list[int] | None = None) -> dict:
    role_exists(db, role)
    bot = (cfg("company.recruiter_bot") or "").lstrip("@")
    if not bot:
        raise AccessError("Bot username is not configured (company.recruiter_bot)")
    i = PanelInvite(token=secrets.token_urlsafe(18), role=role, branch_scope=branch_scope, can_see_payroll=can_see_payroll,
                    created_by=scope.actor, expires_at=datetime.now() + timedelta(hours=24))
    db.add(i)
    db.flush()
    audit(db, scope, "user_invite", f"invite:{i.id}", role=role)
    return {**invite_row(i), "link": f"https://t.me/{bot}?start=join_{i.token}"}


def invites(db: Session, limit: int = 200) -> list[dict]:
    now_ = datetime.now()
    out = []
    for i in db.scalars(select(PanelInvite).order_by(PanelInvite.id.desc()).limit(limit)):
        if i.status == "open" and i.expires_at < now_:
            i.status = "expired"
        out.append(invite_row(i))
    return out


def approve_invite(db: Session, scope: Scope, iid: int, username: str | None = None, full_name: str | None = None) -> dict:
    i = db.get(PanelInvite, iid)
    if not i or i.status != "pending" or not i.telegram_id:
        raise AccessError("Nothing to approve: the person has not opened the link yet, or it is already decided")
    if username and not USERNAME_RE.match(username):
        raise AccessError("Login: 3-60 latin letters, digits, _ . -")
    username = username or re.sub(r"[^a-z0-9_.-]", "", (i.tg_username or f"tg{i.telegram_id}").lower()) or f"tg{i.telegram_id}"
    if db.scalar(select(User.id).where(User.username == username)):
        raise AccessError(f"Login '{username}' is taken: give another one")
    password = secrets.token_urlsafe(9)
    u = User(username=username, full_name=full_name or i.tg_name or username, password_hash=hash_password(password),
             role=i.role, branch_scope=i.branch_scope, can_see_payroll=i.can_see_payroll, telegram_id=i.telegram_id)
    db.add(u)
    db.flush()
    i.status, i.user_id = "approved", u.id
    _notify(db, i.telegram_id, _login_text(username, password))  # only to the person's own chat
    audit(db, scope, "user_invite_approve", f"user:{u.username}", role=u.role)
    return user_row(u)


def reject_invite(db: Session, scope: Scope, iid: int) -> dict:
    i = db.get(PanelInvite, iid)
    if not i or i.status not in ("open", "pending"):
        raise AccessError("Invite not found or already decided")
    i.status = "rejected"
    audit(db, scope, "user_invite_reject", f"invite:{i.id}")
    return invite_row(i)


def invite_used_notice(db: Session, i: PanelInvite) -> None:
    """The person opened the link: tell whoever made it in the bot, so they can approve in words."""
    if tg := _tg_of(i.created_by or ""):
        who = i.tg_name + (f" (@{i.tg_username})" if i.tg_username else "")
        _notify(db, tg, f"🔑 {who} panel havolasini ochdi (rol: {i.role}, so'rov #{i.id}). Tasdiqlaysizmi? "
                        f"/ открыл ссылку в панель (роль: {i.role}, запрос #{i.id}). Подтвердить?")


def create_user(db: Session, scope: Scope, username: str, role: str, full_name: str = "", can_see_payroll: bool = False,
                branch_scope: list[int] | None = None, password: str | None = None, deliver_to: int | None = None) -> dict:
    """Panel login. With no password one is generated and sent to `deliver_to` (default: the creator's Telegram)."""
    if not USERNAME_RE.match(username or ""):
        raise AccessError("Login: 3-60 latin letters, digits, _ . -")
    role_exists(db, role)
    if db.scalar(select(User.id).where(User.username == username)):
        raise AccessError(f"Login '{username}' is taken")
    if password is not None and len(password) < 10:
        raise AccessError("Password: at least 10 characters")
    to = deliver_to or _tg_of(scope.actor)
    if password is None and to is None:
        raise AccessError("Nowhere to send the generated password")
    pw = password or secrets.token_urlsafe(9)
    u = User(username=username, full_name=full_name, password_hash=hash_password(pw), role=role,
             branch_scope=branch_scope, can_see_payroll=can_see_payroll)
    db.add(u)
    db.flush()
    if password is None:
        _notify(db, to, _login_text(username, pw))
    audit(db, scope, "user_create", f"user:{u.username}", role=u.role)
    return user_row(u)


def update_user(db: Session, scope: Scope, u: User, *, full_name: str | None = None, role: str | None = None,
                branch_scope: list[int] | None = ..., can_see_payroll: bool | None = None, active: bool | None = None,
                password: str | None = None, reset_password: bool = False) -> dict:
    if u.username == "admin" and (active is False or role not in (None, "admin")):
        raise AccessError("The main admin cannot be disabled or demoted")
    fields = []
    if role is not None:
        role_exists(db, role)
        u.role = role
        fields.append("role")
    for k, v in (("full_name", full_name), ("can_see_payroll", can_see_payroll), ("active", active)):
        if v is not None:
            setattr(u, k, v)
            fields.append(k)
    if branch_scope is not ...:
        u.branch_scope = branch_scope
        fields.append("branch_scope")
    if password:
        if len(password) < 10:
            raise AccessError("Password: at least 10 characters")
        u.password_hash = hash_password(password)
        fields.append("password")
    elif reset_password:
        to = u.telegram_id or _tg_of(scope.actor)
        if to is None:
            raise AccessError("Nowhere to send the new password")
        pw = secrets.token_urlsafe(9)
        u.password_hash = hash_password(pw)
        _notify(db, to, _login_text(u.username, pw))
        fields.append("password")
    audit(db, scope, "user_update", f"user:{u.username}", fields=sorted(fields))
    return user_row(u)


def roles(db: Session) -> list[dict]:
    return [{"code": r.code, "name": r.name, "perms": r.perms, "system": r.system}
            for r in db.scalars(select(Role).order_by(Role.id))]


def set_role(db: Session, scope: Scope, code: str, perms: list[str], name: str | None = None) -> dict:
    """Create a role or replace its permissions. '*' = everything (main admin level)."""
    code = re.sub(r"[^a-z0-9_]+", "_", (code or "").lower()).strip("_")[:40]
    if not code:
        raise AccessError("Role code is empty")
    if code == "admin":
        raise AccessError("The main admin role cannot be changed")
    bad = [p for p in perms if p != "*" and p not in PERMISSIONS]
    if bad:
        raise AccessError(f"Unknown permissions: {', '.join(bad)}. Known: *, {', '.join(PERMISSIONS)}")
    perms = ["*"] if "*" in perms else sorted(set(perms))
    r = db.scalar(select(Role).where(Role.code == code))
    if r is None:
        r = Role(code=code, name=name or code, perms=perms, system=False)
        db.add(r)
    else:
        r.perms = perms
        if name:
            r.name = name
    db.flush()
    audit(db, scope, "role_set", f"role:{code}", perms=perms)
    return {"code": r.code, "name": r.name, "perms": r.perms}
