"""Rule: late N times this month -> private message to the owner; repeats at 2N; no flood for people already over."""
from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services import discipline_alerts as da


def test_rule_crossings(db):
    counts = {1: ("Ali Valiyev", 2), 2: ("Vali Aliyev", 5)}
    with patch.object(da, "_late_counts", lambda db, month: counts):
        assert da.check(db) == []                                   # off by default
        da.save(db, True, 3, "owner", today=date(2026, 10, 30))      # Vali already has 5: not re-announced
        assert da.check(db, date(2026, 10, 30)) == []
        counts[1] = ("Ali Valiyev", 3)                               # Ali reaches 3 -> one message per owner
        msgs = da.check(db, date(2026, 10, 30))
        assert msgs and all("Ali Valiyev" in t and "3-marta" in t for _, t in msgs)
        assert da.check(db, date(2026, 10, 30)) == []                # no repeat at the same level
        counts[2] = ("Vali Aliyev", 6)                               # 2N -> again
        assert any("Vali Aliyev" in t for _, t in da.check(db, date(2026, 10, 30)))
        counts[1] = ("Ali Valiyev", 3)
        assert any("Ali Valiyev" in t for _, t in da.check(db, date(2026, 11, 2)))  # new month starts from zero


def test_rule_api_permission(db):
    c = TestClient(app)
    tok = lambda u, p: {"Authorization": "Bearer " + c.post("/api/auth/login", json={"username": u, "password": p}).json()["token"]}  # noqa: E731
    hr = tok("hr", "demo12345")
    r = c.put("/api/nudges/lateness-rule", headers=hr, json={"enabled": True, "late_count": 3, "to": "owner"})
    assert r.status_code == 200 and r.json()["rule"]["enabled"] is True
    assert c.get("/api/nudges/lateness-rule", headers=tok("buh", "demo12345")).status_code == 403
