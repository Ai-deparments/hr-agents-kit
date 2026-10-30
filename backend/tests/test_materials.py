"""Onboarding materials: upload, send through the bot outbox, talks."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Employee, Outbox

c = TestClient(app)


def _login(u, p):
    r = c.post("/api/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_material_upload_send_and_talk(db):
    hr = _login("hr", "demo12345")
    assert c.post("/api/onboarding/materials", headers=hr, data={"title": "No file"}).status_code == 400
    assert c.post("/api/onboarding/materials", headers=hr, data={"title": "Bad", "url": "http://x"}).status_code == 400
    bad = c.post("/api/onboarding/materials", headers=hr, data={"title": "Exe"}, files={"file": ("a.exe", b"MZ")})
    assert bad.status_code == 400
    r = c.post("/api/onboarding/materials", headers=hr, data={"title": "Kassa standarti", "description": "5 daqiqa"},
               files={"file": ("../kassa.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["kind"] == "video" and m["filename"] == "kassa.mp4"
    linked = list(db.scalars(select(Employee).where(Employee.telegram_id.is_not(None), Employee.status != "fired")))[:2]
    ids = [e.id for e in linked]
    assert c.post(f"/api/onboarding/materials/{m['id']}/send", headers=hr,
                  json={"employee_ids": ids, "talk_employee_ids": ids[:1]}).status_code == 400  # talk needs time + who
    s = c.post(f"/api/onboarding/materials/{m['id']}/send", headers=hr, json={
        "employee_ids": ids, "talk_employee_ids": ids[:1], "talk_at": "2026-11-02T10:00", "talk_with": "HR Dilnoza"})
    assert s.status_code == 200 and s.json()["queued"] == 2
    out = list(db.scalars(select(Outbox).where(Outbox.telegram_id == linked[0].telegram_id).order_by(Outbox.id.desc())))[0]
    assert out.file_path and "Beseda" not in out.text and "02.11.2026 10:00" in out.text
    sends = c.get(f"/api/onboarding/materials/{m['id']}/sends", headers=hr).json()
    talk = next(x for x in sends if x["talk_at"])
    assert c.post(f"/api/onboarding/materials/sends/{talk['id']}/talk-done", headers=hr, json={"note": "ok"}).status_code == 200
    lst = next(x for x in c.get("/api/onboarding/materials", headers=hr).json() if x["id"] == m["id"])
    assert (lst["sent"], lst["talks"], lst["talks_done"]) == (2, 1, 1)
    assert c.post(f"/api/onboarding/materials/{m['id']}/send", headers=_login("buh", "demo12345"),
                  json={"employee_ids": ids}).status_code == 403
