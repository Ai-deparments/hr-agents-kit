"""AI camera webhook -> attendance."""
import hashlib
import hmac
import json
import time
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.main import app
from app.models import AttendanceEvent, Branch, CameraDelivery, CameraEvent, Employee, Position
from app.rbac import Scope
from app.services import attendance as att
from app.services import camera, reports, schedules

c = TestClient(app)
SECRET = "camera-test-secret-0123456789abcdef"
OWNER = Scope("test", "owner", None, True)


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setattr(settings(), "camera_webhook_secret", SECRET)
    return SECRET


def _post(body: dict, delivery: str, ts: int | None = None, secret: str = SECRET, raw: bytes | None = None):
    raw = raw if raw is not None else json.dumps(body).encode()
    ts = ts or int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    return c.post("/api/webhooks/camera", content=raw, headers={"X-Signature": f"sha256={sig}", "X-Timestamp": str(ts),
                                                                "X-Delivery-Id": delivery, "Content-Type": "application/json"})


def _emp(db, name, sched="day_9_18"):
    b = db.scalar(select(Branch).where(Branch.code == "P02"))
    p = db.scalar(select(Position).where(Position.code == "cashier"))
    e = Employee(full_name=name, branch_id=b.id, position_id=p.id, hire_date=date(2025, 1, 1), schedule_code=sched)
    db.add(e)
    db.commit()
    return e


def _workday(e, start: date) -> date:
    d = start
    while not schedules.is_workday(e, d):
        d -= timedelta(days=1)
    return d


def test_not_configured_is_503(monkeypatch):
    monkeypatch.setattr(settings(), "camera_webhook_secret", "")
    assert _post({"event": "test"}, "d-off").status_code == 503


def test_signature_window_and_size(secret):
    assert _post({"event": "test"}, "d-sig-1", secret="wrong-secret").status_code == 401
    assert _post({"event": "test"}, "d-sig-2", ts=int(time.time()) - 301).status_code == 401
    r = c.post("/api/webhooks/camera", content=b"{}", headers={"X-Delivery-Id": "d-sig-3"})
    assert r.status_code == 401
    assert _post({}, "d-big", raw=b'{"event":"test","pad":"' + b"x" * (600 * 1024) + b'"}').status_code == 413
    assert _post({"event": "test"}, "d-sig-ok").json()["ok"] is True


def test_arrival_earliest_leave_latest_and_dedupe(secret, db):
    e = _emp(db, "Kamola Testova")
    d = _workday(e, date.today() - timedelta(days=1))
    t = datetime.combine(d, datetime.min.time())
    for i, (ev, hhmm) in enumerate([("staff.arrived", "09:20"), ("staff.arrived", "09:05"), ("staff.arrived", "09:40"),
                                    ("staff.left", "17:00"), ("staff.left", "18:10"), ("staff.left", "17:30")]):
        body = {"event": ev, "data": {"full_name": "testova  KAMOLA", "time": f"{d.isoformat()}T{hhmm}:00",
                                      "photo": "data:image/jpeg;base64,AAAA"}}
        assert _post(body, f"d-ar-{e.id}-{i}").status_code == 200
    again = _post({"event": "staff.arrived", "data": {"full_name": "Kamola Testova", "time": f"{d}T08:00:00"}}, f"d-ar-{e.id}-0")
    assert again.json()["duplicate"] is True  # the retried delivery did not move arrival to 08:00
    db.expire_all()
    marks = list(db.scalars(select(AttendanceEvent).where(AttendanceEvent.employee_id == e.id, AttendanceEvent.source == "camera")))
    assert sorted((m.kind, m.ts.strftime("%H:%M")) for m in marks) == [("in", "09:05"), ("out", "18:10")]
    r = att.compute_day(e, d, att.AttendanceData(db, [e.id], d, d), now=t + timedelta(days=2))
    assert r.source == "camera" and r.status == "present" and r.worked_hours == 8.08
    # photos are never stored
    stored = db.scalar(select(CameraDelivery).where(CameraDelivery.delivery_id == f"d-ar-{e.id}-0"))
    assert "photo" not in json.dumps(stored.payload)


def test_human_mark_wins_over_camera(secret, db):
    e = _emp(db, "Javlon Humanov")
    d = _workday(e, date.today() - timedelta(days=1))
    t = datetime.combine(d, datetime.min.time())
    db.add(AttendanceEvent(employee_id=e.id, kind="in", ts=t + timedelta(hours=9, minutes=30), source="telegram"))
    db.commit()
    _post({"event": "staff.arrived", "data": {"full_name": "Javlon Humanov", "time": f"{d}T08:50:00"}}, f"d-h-{e.id}-1")
    _post({"event": "staff.left", "data": {"full_name": "Javlon Humanov", "time": f"{d}T18:30:00"}}, f"d-h-{e.id}-2")
    r = att.compute_day(e, d, att.AttendanceData(db, [e.id], d, d), now=t + timedelta(days=2))
    assert r.check_in.endswith("09:30") and r.source == "telegram"  # human check-in beats the earlier camera arrival
    assert r.check_out.endswith("18:30")  # no human check-out -> camera leave fills the gap


def test_unmatched_and_ambiguous_are_stored_not_guessed(secret, db):
    _emp(db, "Twin Same")
    _emp(db, "Twin Same")
    d = date.today()
    _post({"event": "staff.arrived", "data": {"full_name": "Twin Same", "time": f"{d}T09:00:00"}}, "d-amb-1")
    _post({"event": "staff.arrived", "data": {"full_name": "Nobody Unknownov", "time": f"{d}T09:00:00"}}, "d-unm-1")
    rows = {x.raw_name: x for x in db.scalars(select(CameraEvent).where(CameraEvent.delivery_id.in_(["d-amb-1", "d-unm-1"])))}
    assert rows["Twin Same"].match == "ambiguous" and rows["Twin Same"].employee_id is None
    assert rows["Nobody Unknownov"].match == "unmatched" and not rows["Nobody Unknownov"].applied
    summary = camera.day_summary(db, OWNER, d)
    assert any("Nobody Unknownov" in n for n in summary["unmatched"])
    head = Scope("tg:1", "manager", {db.scalar(select(Branch).where(Branch.code == "P02")).id})
    assert camera.day_summary(db, head, d)["unmatched"] is None  # names never reach branch scopes


def test_visits_timesheet_and_bad_payloads(secret, db):
    d = date.today()
    assert _post({"event": "visits.hour", "data": {"date": d.isoformat(), "hour": 10, "count": 7, "branch_code": "P02"}}, "d-v1").status_code == 200
    assert _post({"event": "visits.hour", "data": {"date": d.isoformat(), "hour": 10, "count": 9, "branch_code": "P02"}}, "d-v2").status_code == 200
    s = camera.day_summary(db, OWNER, d)
    assert {"hour": 10, "count": 9} in s["hourly_visits"]
    e = _emp(db, "Sevara Tabelova")
    day = _workday(e, d - timedelta(days=2))
    r = _post({"event": "timesheet.day", "data": {"date": day.isoformat(), "rows": [
        {"full_name": "Sevara Tabelova", "first_in": f"{day}T09:01:00", "last_out": f"{day}T18:05:00"}]}}, "d-ts1")
    assert r.json()["result"] == {"matched": 2}
    assert _post({"event": "staff.arrived", "data": {}}, "d-bad1").status_code == 422
    assert _post({"event": "nope"}, "d-bad2").status_code == 422
    assert _post({"event": "visits.hour", "data": {"date": "x", "hour": 99, "count": 1}}, "d-bad3").status_code == 422


def test_camera_line_counts_in_group_names_only_private(secret, db):
    d = date.today()
    _post({"event": "staff.arrived", "data": {"full_name": "Stranger Danger", "time": f"{d}T09:00:00"}}, "d-rep-1")
    for group in (reports.morning_text(db, OWNER, d), reports.morning_md(db, OWNER, d), reports.evening_md(db, OWNER, d)):
        assert "Kamera: keldi" in group and "tanilmadi" in group and "Stranger Danger" not in group
    private = reports.camera_unmatched_text(db, d)
    assert "Stranger Danger" in private


def test_strip_images_any_depth():
    blob = "A" * 300
    out = camera.strip_images({"a": {"face_image": "x", "list": [blob, "ok"], "note": "short text"}, "snapshot": "y"})
    assert out == {"a": {"list": ["ok"], "note": "short text"}}


def test_camera_page_permissions(secret):
    h = {"Authorization": f"Bearer {c.post('/api/auth/login', json={'username': 'regional', 'password': 'demo12345'}).json()['token']}"}
    r = c.get("/api/camera", headers=h)
    assert r.status_code == 200 and r.json()["unmatched"] is None
    assert c.get("/api/camera").status_code == 401
