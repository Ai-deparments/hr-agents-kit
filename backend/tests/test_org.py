"""Roles builder, departments, bot registrations, bot functions, broadcast."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Employee, Outbox, Registration
from app.rbac import scope_for_telegram

c = TestClient(app)


def _login(u, p):
    r = c.post("/api/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_only_main_admin_builds_roles_and_departments():
    hr = _login("hr", "demo12345")
    assert c.get("/api/roles", headers=hr).status_code == 403
    assert c.post("/api/departments", headers=hr, json={"name": "IT"}).status_code == 403
    assert c.get("/api/departments", headers=hr).status_code == 200
    admin = _login("admin", "admin12345")
    assert c.post("/api/departments", headers=admin, json={"name": "IT"}).status_code == 200
    ceo = _login("ceo", "demo12345")  # CEO session = full access
    assert c.get("/api/roles", headers=ceo).status_code == 200


def test_custom_role_controls_panel_access():
    admin = _login("admin", "admin12345")
    assert c.post("/api/roles", headers=admin, json={"name": "Bad", "perms": ["root"]}).status_code == 400
    r = c.post("/api/roles", headers=admin, json={"name": "Onboarding lead", "perms": ["hr.read", "onboarding"]})
    assert r.status_code == 200, r.text
    role = r.json()
    u = c.post("/api/users", headers=admin, json={"username": "onb", "password": "onboarding123", "role": role["code"]})
    assert u.status_code == 200, u.text
    h = _login("onb", "onboarding123")
    me = c.get("/api/me", headers=h).json()
    assert set(me["perms"]) == {"hr.read", "onboarding"}
    assert c.get("/api/employees", headers=h).status_code == 200
    assert c.post("/api/positions", headers=h, json={"title": "Tester"}).status_code == 403
    # the admin widens the role -> applies on the next request, no re-login
    c.patch(f"/api/roles/{role['id']}", headers=admin, json={"name": role["name"], "perms": ["hr.read", "hr.write"]})
    assert c.post("/api/positions", headers=h, json={"title": "Tester"}).status_code == 200
    assert c.delete(f"/api/roles/{role['id']}", headers=admin).status_code == 409  # still assigned
    sysrole = next(x for x in c.get("/api/roles", headers=admin).json() if x["code"] == "hr_manager")
    assert c.delete(f"/api/roles/{sysrole['id']}", headers=admin).status_code == 409


def test_main_admin_cannot_be_disabled():
    admin = _login("admin", "admin12345")
    uid = next(u["id"] for u in c.get("/api/users", headers=admin).json() if u["username"] == "admin")
    assert c.patch(f"/api/users/{uid}", headers=admin, json={"active": False}).status_code == 409


def test_registration_approve_links_employee_and_opens_functions(db):
    hr = _login("hr", "demo12345")
    regs = c.get("/api/registrations", headers=hr).json()
    assert len(regs) >= 3
    reg = regs[-1]
    branch = c.get("/api/dictionaries", headers=hr).json()["branches"][0]["id"]
    assert c.post(f"/api/registrations/{reg['id']}/approve", headers=hr,
                  json={"functions": ["nope"], "branch_id": branch}).status_code == 400
    r = c.post(f"/api/registrations/{reg['id']}/approve", headers=hr, json={"functions": ["helpdesk"], "branch_id": branch})
    assert r.status_code == 200, r.text
    assert c.post(f"/api/registrations/{reg['id']}/approve", headers=hr, json={"branch_id": branch}).status_code == 404
    e = db.scalar(select(Employee).where(Employee.telegram_id == reg["telegram_id"]))
    assert e and e.bot_functions == ["helpdesk"]
    assert db.scalar(select(Outbox).where(Outbox.telegram_id == reg["telegram_id"]))
    scope = scope_for_telegram(db, reg["telegram_id"])
    assert scope.has_function("suhayl") and not scope.has_function("bexruz")
    assert scope_for_telegram(db, 9999).has_function("bexruz")  # owner: everything


def test_registration_reject_needs_reason(db):
    hr = _login("hr", "demo12345")
    reg = c.get("/api/registrations", headers=hr).json()[0]
    assert c.post(f"/api/registrations/{reg['id']}/reject", headers=hr, json={"reason": ""}).status_code == 422
    assert c.post(f"/api/registrations/{reg['id']}/reject", headers=hr, json={"reason": "Not our staff"}).status_code == 200
    assert db.get(Registration, reg["id"]).status == "rejected"
    assert c.get("/api/registrations", headers=_login("recruiter", "demo12345")).status_code == 403


def test_broadcast_reaches_only_linked_people_in_scope(db):
    hr = _login("hr", "demo12345")
    n = c.post("/api/broadcast", headers=hr, json={"text": "Ertaga yig'ilish 10:00"}).json()["queued"]
    linked = len(list(db.scalars(select(Employee.id).where(Employee.telegram_id.is_not(None), Employee.status != "fired"))))
    assert 0 < n <= linked
    assert c.post("/api/broadcast", headers=_login("buh", "demo12345"), json={"text": "hi there"}).status_code == 403
