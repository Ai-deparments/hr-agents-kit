"""Panel access from the bot: invites, logins, roles; passwords only via Outbox, never in tool output; private chat only."""
import json
import uuid

from sqlalchemy import select

from app.agents.registry import AGENTS
from app.agents.tools import TOOLS, Ctx, execute, tools_for
from app.auth import check_password
from app.bots.main import _use_invite
from app.models import Outbox, PanelInvite, Role, User
from app.rbac import Scope

HR = Scope("tg:7001", "hr_head", None, True)


def run(db, name, args=None, scope=HR):
    return json.loads(execute(Ctx(db, scope, "hr"), TOOLS[name], args or {}))


def _last_outbox(db, tg):
    return db.scalars(select(Outbox).where(Outbox.telegram_id == tg).order_by(Outbox.id.desc())).first()


class _TgUser:
    def __init__(self, uid):
        self.id, self.first_name, self.last_name, self.username = uid, "Nodira", "Karimova", f"nodira{uid}"


def test_invite_open_notice_approve_sends_login_to_person_only(db):
    out = run(db, "panel_invite", {"role": "recruiter"})
    assert out["link"].startswith("https://t.me/") and "join_" in out["link"]
    token = out["link"].split("join_")[1]
    uid = 880000 + uuid.uuid4().int % 9999
    assert _use_invite(_TgUser(uid), token)
    db.expire_all()
    notice = _last_outbox(db, 7001)
    assert notice and f"#{out['invite_id']}" in notice.text  # the inviter is told in the bot
    res = run(db, "panel_invite_decide", {"invite_id": out["invite_id"], "approve": True})
    assert res["role"] == "recruiter" and set(res) == {"login", "role", "note"}
    msg = _last_outbox(db, uid)
    assert msg and f"Login: {res['login']}" in msg.text
    pw = msg.text.split("Parol / Пароль: ")[1].split("\n")[0]
    u = db.scalar(select(User).where(User.username == res["login"]))
    assert check_password(u, pw) and u.telegram_id == uid and pw not in json.dumps(res)
    assert "error" in run(db, "panel_invite_decide", {"invite_id": out["invite_id"], "approve": True})  # once only


def test_user_create_password_goes_to_asker_privately(db):
    login = f"ceo_{uuid.uuid4().hex[:6]}"
    res = run(db, "panel_user_create", {"username": login, "role": "ceo", "full_name": "Bosh direktor"})
    assert res["login"] == login and res["role"] == "ceo"
    msg = _last_outbox(db, 7001)
    pw = msg.text.split("Parol / Пароль: ")[1].split("\n")[0]
    assert pw not in json.dumps(res) and len(pw) >= 10
    assert check_password(db.scalar(select(User).where(User.username == login)), pw)
    assert "taken" in run(db, "panel_user_create", {"username": login, "role": "ceo"})["error"]
    assert "error" in run(db, "panel_user_create", {"username": "bad login!", "role": "ceo"})
    assert "Unknown role" in run(db, "panel_user_create", {"username": f"x{login}", "role": "nope"})["error"]


def test_user_update_and_admin_protected(db):
    login = f"hrm_{uuid.uuid4().hex[:6]}"
    run(db, "panel_user_create", {"username": login, "role": "recruiter"})
    res = run(db, "panel_user_update", {"username": login, "role": "hr_manager", "can_see_payroll": True})
    assert res["role"] == "hr_manager" and res["can_see_payroll"] is True
    assert run(db, "panel_user_update", {"username": login, "active": False})["active"] is False
    assert "cannot" in run(db, "panel_user_update", {"username": "admin", "active": False})["error"]
    assert "error" in run(db, "panel_user_update", {"username": "ghost_user"})


def test_role_set_everything_and_validation(db):
    res = run(db, "panel_role_set", {"code": "boss_test", "perms": ["hr.read", "*"]})  # not hr_manager: shared test DB
    assert res["perms"] == ["*"]
    assert db.scalar(select(Role).where(Role.code == "boss_test")).perms == ["*"]
    new = run(db, "panel_role_set", {"code": "Kadrlar", "perms": ["hr.read", "documents"], "name": "Kadrlar bo'limi"})
    assert new["code"] == "kadrlar" and new["perms"] == ["documents", "hr.read"]
    assert "Unknown permissions" in run(db, "panel_role_set", {"code": "x", "perms": ["root"]})["error"]
    assert "cannot" in run(db, "panel_role_set", {"code": "admin", "perms": ["hr.read"]})["error"]
    listing = run(db, "panel_access")
    assert {"users", "invites", "roles", "permissions"} <= set(listing) and "password_hash" not in json.dumps(listing)


def test_only_hr_head_and_never_in_group(db):
    names = AGENTS["hr"].tools
    mgr = Scope("tg:5", "manager", None, False)
    assert not {t.name for t in tools_for(names, mgr)} & {"panel_invite", "panel_user_create"}
    grp = Scope("tg:7001", "hr_head", None, True, channel="group")
    assert not {t.name for t in tools_for(names, grp)} & {"panel_access", "panel_invite", "panel_role_set"}
    assert "error" in run(db, "panel_invite", {"role": "ceo"}, scope=grp)  # forced call is refused too
    assert "error" in run(db, "panel_invite", {"role": "ceo"}, scope=mgr)
    assert {"panel_invite", "panel_user_create"} <= {t.name for t in tools_for(names, HR)}
    assert db.scalar(select(PanelInvite).where(PanelInvite.created_by == "tg:5")) is None
