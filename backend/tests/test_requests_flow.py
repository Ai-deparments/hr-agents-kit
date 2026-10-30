"""Employee requests: notice to HR, HR decides in words, the employee gets the answer (+ PDF)."""
import dataclasses
import json
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.agents.tools import TOOLS, Ctx, execute
from app.config import settings
from app.models import Employee, LeaveRequest, Outbox
from app.rbac import Scope, scope_for_telegram
from app.services import people, requests_flow

HR_TG, EMP_TG = 9999, 555001  # 9999 = owner (conftest)


@pytest.fixture
def emp(db):
    e = db.scalar(select(Employee).where(Employee.telegram_id == EMP_TG))  # decisions commit: reuse across tests
    if not e:
        e = db.scalar(select(Employee).where(Employee.status != "fired", Employee.telegram_id.is_(None)))
        e.telegram_id = EMP_TG
    db.flush()
    return e


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setattr(requests_flow, "docs_dir", lambda: tmp_path)
    monkeypatch.setattr(requests_flow, "settings", lambda: dataclasses.replace(settings(), report_chat_id=-100))


def _req(db, emp, kind, **kw):
    return people.create_request(db, Scope("tg:x", "owner", None, True), emp, kind, **kw)


def test_creation_notice_goes_to_hr_topic(db, emp):
    out = json.loads(execute(Ctx(db, scope_for_telegram(db, EMP_TG), "suhayl"), TOOLS["create_my_request"],
                             {"kind": "certificate", "comment": "bank uchun"}))
    rid = out["request_id"]
    n = db.scalar(select(Outbox).where(Outbox.text.like(f"%So'rov #{rid} %")))
    assert n and n.telegram_id == -100 and n.topic == "attendance"
    assert emp.full_name in n.text and "tasdiqlayman" in n.text


def test_parse_words():
    notice = "📝 So'rov #12 · Ali — ta'til"
    assert requests_flow.parse("tasdiqlayman", notice) == (12, True, "")
    assert requests_flow.parse("rad: ish ko'p", notice) == (12, False, "ish ko'p")
    assert requests_flow.parse("so'rov 7 tasdiqla") == (7, True, "")
    assert requests_flow.parse("#8 rad: grafik band") == (8, False, "grafik band")
    assert requests_flow.parse("заявка 9 одобряю") == (9, True, "")
    assert requests_flow.parse("kim kech qoldi?") is None
    assert requests_flow.parse("ok", "boshqa xabar") is None
    assert requests_flow.parse("bu haqda o'ylab ko'raman", notice) is None


def test_hr_approves_certificate_by_reply(db, emp):
    r = _req(db, emp, "certificate")
    res = requests_flow.handle(db, scope_for_telegram(db, HR_TG), "tasdiqlayman", requests_flow.notice_text(r))
    assert res["status"] == "approved" and res["sent"]
    db.refresh(r)
    assert r.status == "approved" and r.decided_by == f"tg:{HR_TG}" and r.decided_at
    o = db.scalar(select(Outbox).where(Outbox.telegram_id == EMP_TG).order_by(Outbox.id.desc()))
    assert o.file_path and o.file_path.endswith(".pdf") and f"#{r.id}" in o.text
    with open(o.file_path, "rb") as f:
        assert f.read(4) == b"%PDF"


def test_vacation_order_goes_to_documents_topic(db, emp):
    emp.leave_balance_days, emp.hire_date = 30, date.today() - timedelta(days=400)
    d = date.today() + timedelta(days=10)
    r = _req(db, emp, "vacation", date_from=d, date_to=d + timedelta(days=4))
    res = requests_flow.handle(db, scope_for_telegram(db, HR_TG), f"so'rov {r.id} ha")
    assert res["status"] == "approved" and res["order"]
    o = db.scalar(select(Outbox).where(Outbox.topic == "documents").order_by(Outbox.id.desc()))
    assert o.telegram_id == -100 and o.file_path.endswith(".pdf")
    mine = db.scalar(select(Outbox).where(Outbox.telegram_id == EMP_TG).order_by(Outbox.id.desc()))
    assert mine.file_path is None and "tasdiqlandi" in mine.text  # the order is not sent to the employee


def test_non_hr_cannot_decide(db, emp):
    r = _req(db, emp, "certificate")
    assert requests_flow.handle(db, scope_for_telegram(db, EMP_TG), "tasdiqlayman", requests_flow.notice_text(r)) is None
    with pytest.raises(people.AccessDenied):
        requests_flow.decide(db, scope_for_telegram(db, EMP_TG), r.id, True)
    db.refresh(r)
    assert r.status == "pending"


def test_reject_with_reason(db, emp):
    r = _req(db, emp, "shift_swap", comment="juma kuni")
    res = requests_flow.handle(db, scope_for_telegram(db, HR_TG), f"#{r.id} rad: smenada odam yetmaydi")
    assert res["status"] == "rejected"
    db.refresh(r)
    assert r.decision_reason == "smenada odam yetmaydi"
    o = db.scalar(select(Outbox).where(Outbox.telegram_id == EMP_TG).order_by(Outbox.id.desc()))
    assert "rad etildi" in o.text and "smenada odam yetmaydi" in o.text
    again = requests_flow.handle(db, scope_for_telegram(db, HR_TG), f"#{r.id} tasdiqlayman")
    assert again["error"] == "Already decided"


def test_decision_must_start_the_message():
    from app.services.requests_flow import parse
    n = "So'rov #12"
    assert parse("tasdiqlayman", n) == (12, True, "")
    assert parse("ok", n) == (12, True, "")
    assert parse("rad: hujjat yo'q", n) == (12, False, "hujjat yo'q")
    assert parse("bilmayman, ok keyin qarayman", n) is None          # "ok" inside a sentence is not an approval
    assert parse("hali emas, ertaga tasdiqlayman", n) is None
    assert parse("ha lekin keyin", n) is None
