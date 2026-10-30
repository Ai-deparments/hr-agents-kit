"""The SPA fallback must never serve files outside web/dist (regression: %2e%2e/.env leaked secrets)."""
import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.mark.skipif(not main.WEB_DIST.exists(), reason="web/dist not built")
@pytest.mark.parametrize("path", ["/..%2f..%2f.env.example", "/%2e%2e/%2e%2e/backend/app/config.py", "/..%2f..%2fREADME.md"])
def test_spa_does_not_leave_dist(path):
    r = TestClient(main.app).get(path)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")  # index.html, not the file
    assert b"JWT_SECRET" not in r.content and b"Runtime settings" not in r.content
