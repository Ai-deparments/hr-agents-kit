"""Positions, regions, branches: edit and delete from the panel; deletes refused while in use or synced."""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import Branch, Employee, ExternalRef

c = TestClient(app)


def _h(user="admin", pw="admin12345"):
    return {"Authorization": "Bearer " + c.post("/api/auth/login", json={"username": user, "password": pw}).json()["token"]}


def test_position_region_branch_edit_and_delete():
    h, tag = _h(), uuid.uuid4().hex[:5]
    p = c.post("/api/positions", headers=h, json={"title": f"Kassir {tag}"}).json()
    r = c.patch(f"/api/positions/{p['id']}", headers=h, json={"title": f"Katta kassir {tag}", "is_manager": True}).json()
    assert r["title"] == f"Katta kassir {tag}" and r["is_manager"] is True
    d = c.get("/api/dictionaries", headers=h).json()
    assert any(x["id"] == p["id"] and x["is_manager"] for x in d["positions"])
    assert c.delete(f"/api/positions/{p['id']}", headers=h).status_code == 200

    reg = c.post("/api/regions", headers=h, json={"name": f"Hudud {tag}"}).json()
    assert c.patch(f"/api/regions/{reg['id']}", headers=h, json={"name": f"Hudud2 {tag}"}).json()["name"] == f"Hudud2 {tag}"
    br = c.post("/api/branches", headers=h, json={"name": f"Filial {tag}", "region_id": reg["id"]}).json()
    assert c.delete(f"/api/regions/{reg['id']}", headers=h).status_code == 409  # a branch uses it
    u = c.patch(f"/api/branches/{br['id']}", headers=h, json={"name": f"Filial2 {tag}", "city": "Toshkent", "mode": "24/7"}).json()
    assert u["name"] == f"Filial2 {tag}" and u["mode"] == "24/7" and u["region_id"] == reg["id"]
    assert c.patch(f"/api/branches/{br['id']}", headers=h, json={"region_id": 999999}).status_code == 400
    assert c.delete(f"/api/branches/{br['id']}", headers=h).status_code == 200
    assert c.delete(f"/api/regions/{reg['id']}", headers=h).status_code == 200


def test_delete_refused_when_used_or_synced():
    h = _h()
    with SessionLocal() as db:
        e = db.scalars(select(Employee).where(Employee.branch_id.is_not(None), Employee.position_id.is_not(None))).first()
        bid, pid = e.branch_id, e.position_id
    rb = c.delete(f"/api/branches/{bid}", headers=h)
    assert rb.status_code == 409 and "employees" in rb.json()["detail"]
    assert c.delete(f"/api/positions/{pid}", headers=h).status_code == 409
    tag = uuid.uuid4().hex[:5]
    p = c.post("/api/positions", headers=h, json={"title": f"TimePay lavozim {tag}"}).json()
    with SessionLocal() as db:
        db.add(ExternalRef(source="timepay", kind="position", external_id=f"t-{tag}", local_id=p["id"]))
        db.commit()
    r = c.delete(f"/api/positions/{p['id']}", headers=h)
    assert r.status_code == 409 and "TimePay" in r.json()["detail"]


def test_rights():
    hr = _h("hr", "demo12345")  # demo HR manager: hr.write, no '*'
    assert c.patch("/api/regions/1", headers=hr, json={"name": "Nomi"}).status_code in (200, 404)
    assert c.delete("/api/positions/1").status_code in (401, 403)
    with SessionLocal() as db:
        assert db.scalar(select(Branch)) is not None
