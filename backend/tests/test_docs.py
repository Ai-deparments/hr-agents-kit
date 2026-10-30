"""HR document templates -> issued doc with real card data, blanks for unknown fields -> PDF."""
from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


def _login(u, p="demo12345"):
    r = c.post("/api/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_issue_pdf(db):
    hr = _login("hr")
    tpls = c.get("/api/hr-docs/templates", headers=hr).json()
    codes = {t["code"]: t for t in tpls}
    assert {"employment_certificate", "hire_order", "leave_order"} <= set(codes)
    assert "leave_from" in codes["leave_order"]["fields"]
    emp = c.get("/api/employees", headers=hr).json()
    emp = (emp["items"] if isinstance(emp, dict) else emp)[0]
    d = c.post("/api/hr-docs", headers=hr, json={"template_id": codes["leave_order"]["id"], "employee_id": emp["id"],
                                                  "extra": {"leave_from": "01.11.2026"}}).json()
    assert emp["full_name"] in d["body"] and "01.11.2026" in d["body"]
    assert "leave_to" in d["missing"] and "________" in d["body"]          # unknown -> blank, never invented
    assert d["number"].startswith("T-")
    r = c.get(f"/api/hr-docs/{d['id']}/pdf", headers=hr)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    d2 = c.post("/api/hr-docs", headers=hr, json={"template_id": codes["leave_order"]["id"], "employee_id": emp["id"]}).json()
    assert d2["number"] != d["number"]
    assert c.get("/api/hr-docs/templates", headers=_login("buh")).status_code == 403
