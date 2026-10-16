from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


def _login(u, p):
    r = c.post("/api/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_login_and_dashboard():
    h = _login("admin", "admin12345")
    d = c.get("/api/dashboard", headers=h).json()
    assert d["active"] > 0 and d["fund"] is not None
    assert c.get("/api/dashboard").status_code == 401


def test_regional_manager_sees_only_his_branches():
    h = _login("regional", "demo12345")
    branches = c.get("/api/dictionaries", headers=h).json()["branches"]
    assert len(branches) == 2
    emps = c.get("/api/employees", headers=h).json()
    assert {e["branch_id"] for e in emps} <= {b["id"] for b in branches}
    assert all(e["base_salary"] is None for e in emps)
    assert c.get("/api/audit", headers=h).status_code == 403


def test_hr_manager_cannot_approve_payroll_or_see_amounts():
    h = _login("hr", "demo12345")
    month = c.get("/api/payroll", headers=h).json()
    assert month["fund"] is None
    assert c.post(f"/api/payroll/{month['month']}/status", json={"status": "approved", "reason": "x" * 5}, headers=h).status_code == 403


def test_payroll_flow_human_only():
    h = _login("buh", "demo12345")
    m = "2026-01"
    assert c.post(f"/api/payroll/{m}/status", json={"status": "approved", "reason": "check"}, headers=h).status_code == 409
    assert c.post(f"/api/payroll/{m}/calculate", headers=h).status_code == 200
    assert c.post(f"/api/payroll/{m}/status", json={"status": "approved", "reason": "checked"}, headers=h).json()["status"] == "approved"


def test_miniapp_dev_checkin_and_lead():
    tok = c.post("/api/miniapp/auth", json={"init_data": ""}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    me = c.get("/api/miniapp/me", headers=h).json()
    assert me["linked"] is True
    r = c.post("/api/miniapp/check", json={"kind": "in"}, headers=h)  # P01 has a geofence: location required
    assert r.status_code == 403 and r.json()["detail"]["need"] == "location"
    far = c.post("/api/miniapp/check", json={"kind": "in", "lat": 41.35, "lon": 69.30, "accuracy": 20}, headers=h)
    assert far.status_code == 403 and far.json()["detail"]["need"] == "qr"
    ok = c.post("/api/miniapp/check", json={"kind": "in", "lat": 41.2757, "lon": 69.2035, "accuracy": 15}, headers=h).json()
    assert ok["ok"] and ok["verified"] == "geo"
    assert c.get("/api/miniapp/lead/branches", headers=h).status_code == 403  # an employee is not a lead


def test_rauf_panel_and_permissions():
    h = _login("recruiter", "demo12345")
    d = c.get("/api/rauf/dashboard", headers=h).json()
    assert d["candidates"] >= 1 and set(d["funnel"]) == {"new", "shortlist", "hired", "rejected"}
    assert set(c.get("/api/rauf/pipeline", headers=h).json()) == {"new", "shortlist", "hired", "rejected"}
    integ = c.get("/api/rauf/integrations", headers=h).json()
    assert all(set(i) <= {"name", "connected", "note"} for i in integ)  # never key values
    assert c.get("/api/rauf/dashboard", headers=_login("buh", "demo12345")).status_code == 403


def test_rauf_miniapp_hr_only():
    tok = c.post("/api/miniapp/auth", json={"init_data": ""}).json()["token"]  # dev user 2001 = employee
    assert c.get("/api/miniapp/rauf/candidates", headers={"Authorization": f"Bearer {tok}"}).status_code == 403


def test_agents_chat_panel():
    h = _login("admin", "admin12345")
    r = c.post("/api/agents/husayn/chat", json={"text": "/shtat"}, headers=h)
    assert r.status_code == 200 and "total" in r.json()["answer"]
