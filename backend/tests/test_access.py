"""Strangers -> silent access requests; reject-all; panel invite via Telegram; last login."""
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.bots import main as bot
from app.main import app
from app.models import Outbox, PanelInvite, Registration

c = TestClient(app)


def _login(u, p):
    r = c.post("/api/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _user(i, name="Ali", last="Vali", uname="ali_v"):
    return SimpleNamespace(id=i, first_name=name, last_name=last, username=uname)


def test_stranger_requests_are_counted_once_and_rejected_silently(db):
    assert bot._record_access(_user(555001), "demo_hr_bot") is True
    assert bot._record_access(_user(555001), "demo_hr_bot") is False
    r = db.scalar(select(Registration).where(Registration.telegram_id == 555001))
    assert r.requests == 2 and r.source == "access" and r.bots == ["demo_hr_bot"]
    hr = _login("hr", "demo12345")
    rows = c.get("/api/registrations", headers=hr).json()
    assert any(x["telegram_id"] == 555001 and x["requests"] == 2 for x in rows)
    n = c.post("/api/registrations/reject-all", headers=hr, json={"reason": "Notanish"}).json()["rejected"]
    assert n >= 1
    assert not db.scalar(select(Outbox).where(Outbox.telegram_id == 555001))  # strangers get silence
    assert bot._record_access(_user(555001), "demo_hr_bot") is False  # rejected: still silent, just counted


def test_invite_via_telegram(db):
    admin = _login("admin", "admin12345")
    inv = c.post("/api/users/invite", headers=admin, json={"role": "hr_manager"}).json()
    token = inv["link"].split("start=join_")[1]
    assert bot._use_invite(_user(777001, "Malika", "", "malika_hr"), token)
    assert not bot._use_invite(_user(777002), token)  # one-time
    pend = [x for x in c.get("/api/users/pending", headers=admin).json() if x["id"] == inv["id"]][0]
    assert pend["status"] == "pending" and pend["tg_username"] == "malika_hr"
    u = c.post(f"/api/users/pending/{inv['id']}/approve", headers=admin, json={}).json()
    assert u["username"] == "malika_hr" and u["telegram_id"] == 777001 and u["role"] == "hr_manager"
    msg = db.scalar(select(Outbox).where(Outbox.telegram_id == 777001))
    assert "Login: malika_hr" in msg.text and "Parol:" in msg.text
    assert c.get("/api/users/pending", headers=_login("hr", "demo12345")).status_code == 403
    me = [x for x in c.get("/api/users", headers=admin).json() if x["username"] == "admin"][0]
    assert me["last_login"] is not None
    assert db.scalar(select(PanelInvite).where(PanelInvite.id == inv["id"])).user_id == u["id"]
