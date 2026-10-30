"""Onboarding course: tags + plan + assign + daily delivery + 'ko'rdim' + agent tools."""
import json
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agents.tools import TOOLS, Ctx, execute
from app.bots import main as bot
from app.main import app
from app.models import Employee, MaterialSend, Outbox
from app.rbac import scope_for_telegram
from app.services import onboarding_media

c = TestClient(app)


def _login(u, p):
    r = c.post("/api/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_course_by_position_and_delivery(db, monkeypatch):
    monkeypatch.setattr(onboarding_media, "_ai_pick", lambda e, lib: None)  # rules only
    hr = _login("hr", "demo12345")
    e = db.scalar(select(Employee).where(Employee.telegram_id == 2001))
    other_pos = e.position_id + 1000
    general = c.post("/api/onboarding/materials", headers=hr, data={"title": "Kompaniya bilan tanishuv", "url": "https://example.com/a"}).json()
    mine = c.post("/api/onboarding/materials", headers=hr, data={"title": "Lavozim darsi", "url": "https://example.com/b",
                                                               "position_ids": str(e.position_id), "day_offset": "2"}).json()
    foreign = c.post("/api/onboarding/materials", headers=hr, data={"title": "Boshqa lavozim", "url": "https://example.com/c",
                                                                  "position_ids": str(other_pos)}).json()
    plan = c.get(f"/api/onboarding/materials/course/{e.id}?ai=false", headers=hr).json()["items"]
    ids = {x["material_id"] for x in plan}
    assert general["id"] in ids and mine["id"] in ids and foreign["id"] not in ids
    r = c.post(f"/api/onboarding/materials/course/{e.id}", headers=hr, json={"items": plan}).json()
    assert r["scheduled"] >= 2 and r["sent_now"] >= 1  # day 0 goes out now, day 2 waits
    later = db.scalar(select(MaterialSend).where(MaterialSend.employee_id == e.id, MaterialSend.material_id == mine["id"]))
    assert later.queued is False and later.scheduled_for == date.today() + timedelta(days=2)
    assert onboarding_media.deliver_due(db, date.today() + timedelta(days=2)) >= 1
    db.commit()
    out = db.scalar(select(Outbox).where(Outbox.telegram_id == 2001).order_by(Outbox.id.desc()))
    assert "ko'rdim" in out.text and out.buttons is None  # agents talk: no buttons
    assert bot._mark_seen(2001)
    prog = c.get(f"/api/onboarding/materials/employee/{e.id}", headers=hr).json()
    assert any(x["viewed_at"] for x in prog["items"])
    mine_tool = json.loads(execute(Ctx(db, scope_for_telegram(db, 2001), "suhayl"), TOOLS["my_materials"], {}))
    assert len(mine_tool["items"]) >= 2
    assert c.get(f"/api/onboarding/materials/course/{e.id}", headers=_login("buh", "demo12345")).status_code == 403
