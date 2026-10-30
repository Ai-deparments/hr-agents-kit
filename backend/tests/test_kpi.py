"""KPI score, ABC / 80-20, apply to payroll, reports upload."""
from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.models import KpiMetric
from app.services import kpi

c = TestClient(app)
MONTH = date.today().strftime("%Y-%m")


def _login(u, p):
    r = c.post("/api/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_score_formula_and_cap():
    up = KpiMetric(id=1, name="sales", direction="up", target=100, weight=50, active=True)
    down = KpiMetric(id=2, name="late", direction="down", target=2, weight=50, active=True)
    assert kpi.score([up, down], {1: 100, 2: 2}) == (100.0, 2)
    assert kpi.score([up, down], {1: 300, 2: 0})[0] == 120.0  # both capped at 1.2
    assert kpi.score([up, down], {1: 50})[0] == 50.0           # only filled metrics count
    assert kpi.score([up, down], {}) == (None, 0)              # nothing filled -> unknown, not 0


def test_grid_and_abc():
    h = _login("hr", "demo12345")
    g = c.get(f"/api/kpi/grid?month={MONTH}", headers=h).json()
    assert g["metrics"] and g["rows"] and g["avg"] is not None
    a = c.get(f"/api/kpi/abc?month={MONTH}&basis=kpi", headers=h).json()
    assert a["n"] > 0 and abs(a["rows"][-1]["cum_share"] - 100) < 0.2
    assert [r["class"] for r in a["rows"]] == sorted(r["class"] for r in a["rows"])  # A..B..C in rank order
    assert a["pareto"]["top_share"] is not None
    assert c.get(f"/api/kpi/abc?month={MONTH}&basis=sales", headers=h).status_code == 403  # hr has no payroll view
    assert c.get(f"/api/kpi/abc?month={MONTH}&basis=sales", headers=_login("buh", "demo12345")).status_code == 200


def test_values_permissions_and_apply():
    hr = _login("hr", "demo12345")  # hr_manager has 'analytics'
    g = c.get(f"/api/kpi/grid?month={MONTH}", headers=hr).json()
    row = g["rows"][0]
    mid = row["metrics"][0]
    assert c.post("/api/kpi/values", headers=hr, json={"month": MONTH, "values": [
        {"employee_id": row["employee_id"], "metric_id": mid, "value": 100}]}).status_code == 200
    assert c.post("/api/kpi/values", headers=_login("recruiter", "demo12345"), json={"month": MONTH, "values": []}).status_code == 403
    assert c.post(f"/api/kpi/{MONTH}/apply", headers=hr, json={"reason": "month end"}).status_code == 403  # payroll only
    buh = _login("buh", "demo12345")
    r = c.post(f"/api/kpi/{MONTH}/apply", headers=buh, json={"reason": "month end"})
    assert r.status_code == 200 and r.json()["applied"] > 0
    pay = c.get(f"/api/payroll?month={MONTH}", headers=buh).json()
    assert any(x["kpi"] for x in pay["rows"])


def test_settings_validation():
    h = _login("hr", "demo12345")
    assert c.put("/api/kpi/settings", headers=h, json={"abc_a": 90, "abc_b": 80}).status_code == 400
    assert c.put("/api/kpi/settings", headers=h, json={"abc_a": 70, "abc_b": 90, "pareto_top": 20}).json()["abc_a"] == 70
    c.put("/api/kpi/settings", headers=h, json={"abc_a": 80, "abc_b": 95, "pareto_top": 20})


def test_report_upload_rules():
    h = _login("hr", "demo12345")
    bad = c.post("/api/kpi/reports", headers=h, files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 400
    ok = c.post("/api/kpi/reports?title=KPI%20oktyabr&kind=kpi", headers=h, files={"file": ("../../evil.csv", b"a,b\n1,2", "text/csv")})
    assert ok.status_code == 200, ok.text
    f = ok.json()
    assert f["filename"] == "evil.csv"
    assert c.get(f"/api/kpi/reports/{f['id']}/download", headers=h).content == b"a,b\n1,2"
    assert c.delete(f"/api/kpi/reports/{f['id']}", headers=h).status_code == 200
