"""KPI in words (create / change metrics, enter values) and dashboard tile explanations."""
import json
import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agents.registry import AGENTS
from app.agents.tools import TOOLS, Ctx, execute, tools_for
from app.main import app
from app.models import Employee, KpiMetric, KpiValue
from app.rbac import Scope

HR = Scope("tg:7201", "hr_head", None, True)


def run(db, name, args, scope=HR):
    return json.loads(execute(Ctx(db, scope, "hr"), TOOLS[name], args))


def test_kpi_metric_create_change_and_value(db):
    name = f"Savdo rejasi {uuid.uuid4().hex[:4]}"
    m = run(db, "kpi_metric_save", {"name": name, "target": 100, "unit": "%", "direction": "up", "weight": 3})
    assert m["saved"] and m["target"] == 100 and m["weight"] == 3
    assert any(x["name"] == name for x in run(db, "kpi_metrics", {})["metrics"])
    ch = run(db, "kpi_metric_save", {"metric_id": m["id"], "target": 120})
    assert ch["target"] == 120 and ch["name"] == name
    e = db.scalars(select(Employee).where(Employee.status != "fired")).first()
    v = run(db, "kpi_value_set", {"employee": f"#{e.id}", "metric": name, "value": 95})
    assert v["saved"] and v["month"] == date.today().strftime("%Y-%m")
    row = db.scalar(select(KpiValue).where(KpiValue.employee_id == e.id, KpiValue.metric_id == m["id"]))
    assert row.value == 95
    run(db, "kpi_value_set", {"employee": f"#{e.id}", "metric": str(m["id"]), "value": None})
    assert db.scalar(select(KpiValue).where(KpiValue.employee_id == e.id, KpiValue.metric_id == m["id"])) is None
    off = run(db, "kpi_metric_save", {"metric_id": m["id"], "active": False})
    assert off["active"] is False
    assert "error" in run(db, "kpi_value_set", {"employee": f"#{e.id}", "metric": name, "value": 1})


def test_kpi_validation_and_rights(db):
    assert "error" in run(db, "kpi_metric_save", {"name": "x"})  # no target
    assert "error" in run(db, "kpi_metric_save", {"name": "Bad weight", "target": 5, "weight": 500})
    assert db.scalar(select(KpiMetric).where(KpiMetric.name == "Bad weight")) is None
    assert "error" in run(db, "kpi_metric_save", {"name": "Lavozimli", "target": 5, "position": "kosmonavt-xyz"})
    mgr = Scope("tg:5", "manager", None, False)
    assert not {t.name for t in tools_for(AGENTS["hr"].tools, mgr)} & {"kpi_metric_save", "kpi_value_set"}
    recruiter_panel = Scope("user:rec", "hr_head", None, False, None, {"recruiting"})
    assert "error" in run(db, "kpi_metric_save", {"name": "Nope", "target": 1}, scope=recruiter_panel)


def test_dashboard_explain_tiles_match_dashboard():
    c = TestClient(app)
    h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"username": "admin", "password": "admin12345"}).json()["token"]}
    d = c.get("/api/dashboard", headers=h).json()
    a = c.get("/api/dashboard/explain/active", headers=h).json()
    assert a["value"] == d["active"] and a["sources"] and a["groups"]
    s = c.get("/api/dashboard/explain/shift", headers=h).json()
    assert s["value"] == f"{d['on_shift_today']} / {d['scheduled_today']}"
    f = c.get("/api/dashboard/explain/fund", headers=h).json()
    assert f["value"] == d["fund"] and f["avg"] == (round(d["fund"] / d["salaried"]) if d["salaried"] else None)
    i = c.get("/api/dashboard/explain/inbox", headers=h).json()
    assert i["value"] == d["registrations_pending"]
    assert c.get("/api/dashboard/explain/nope", headers=h).status_code == 404
    assert c.get("/api/dashboard/explain/active").status_code in (401, 403)
