"""Discipline nudges: drafted from last week's lateness, sent only by HR."""
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Employee, Nudge, Outbox

c = TestClient(app)


def _login(u, p="demo12345"):
    return {"Authorization": f"Bearer {c.post('/api/auth/login', json={'username': u, 'password': p}).json()['token']}"}


def test_nudge_flow(db):
    hr = _login("hr")
    e = db.scalar(select(Employee).where(Employee.telegram_id.is_not(None)))
    monday = (date.today() - timedelta(days=date.today().weekday() + 7)).isoformat()
    n = Nudge(employee_id=e.id, week=monday, late_days=3, late_min=90, text="Assalomu alaykum! test")
    db.add(n)
    db.commit()
    assert c.post("/api/nudges/draft", headers=hr).status_code == 200
    assert any(r["id"] == n.id for r in c.get("/api/nudges", headers=hr).json())
    assert c.patch(f"/api/nudges/{n.id}", headers=hr, json={"text": "Tahrirlangan matn"}).status_code == 200
    assert db.scalar(select(Outbox).where(Outbox.text == "Tahrirlangan matn")) is None   # nothing out before HR sends
    assert c.post("/api/nudges/send", headers=hr, json={"ids": [n.id]}).json()["sent"] == 1
    assert db.scalar(select(Outbox).where(Outbox.text == "Tahrirlangan matn")).telegram_id == e.telegram_id
    assert c.post("/api/nudges/send", headers=hr, json={"ids": [n.id]}).json()["sent"] == 0  # no double send
    assert c.get("/api/nudges", headers=_login("buh")).status_code == 403
