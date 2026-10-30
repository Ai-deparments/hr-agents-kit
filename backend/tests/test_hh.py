"""hh.uz search: permission, demo mode, take into candidates once."""
from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


def _login(u, p):
    r = c.post("/api/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_hh_needs_permission_and_connection(monkeypatch):
    monkeypatch.delenv("HH_DEMO", raising=False)
    monkeypatch.delenv("HH_TOKEN_FILE", raising=False)
    assert c.get("/api/hh/status", headers=_login("buh", "demo12345")).status_code == 403
    rec = _login("recruiter", "demo12345")
    assert c.get("/api/hh/status", headers=rec).json()["ok"] is False
    assert c.get("/api/hh/search?text=farmatsevt", headers=rec).status_code == 400  # not connected -> clear error


def test_hh_demo_search_and_take(monkeypatch):
    monkeypatch.setenv("HH_DEMO", "1")
    rec = _login("recruiter", "demo12345")
    r = c.get("/api/hh/search?text=farmatsevt", headers=rec).json()
    assert r["mode"] == "demo" and r["items"]
    it = r["items"][0]
    body = {"hh_id": it["id"], "title": it["title"], "url": "javascript:alert(1)"}
    t = c.post("/api/hh/take", headers=rec, json=body)
    assert t.status_code == 200, t.text
    assert c.post("/api/hh/take", headers=rec, json=body).status_code == 409
    assert next(x for x in c.get("/api/hh/search?text=farmatsevt", headers=rec).json()["items"] if x["id"] == it["id"])["taken"]
    cand = next(x for x in c.get("/api/candidates", headers=rec).json() if x["id"] == t.json()["id"])
    assert cand["source"] == "hh" and cand["breakdown"]["hh_url"] is None  # non-hh URL dropped


def test_demo_turns_off_when_token_appears(monkeypatch, tmp_path):
    from app.services import hh
    f = tmp_path / "hh_token.json"
    monkeypatch.setenv("HH_DEMO", "1")
    monkeypatch.setenv("HH_TOKEN_FILE", str(f))
    assert hh.demo()
    f.write_text('{"access_token": "x", "expires_at": 9999999999}')
    assert not hh.demo() and hh.status()["mode"] == "live"
