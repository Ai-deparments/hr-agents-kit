"""hh.uz post: prepared by the agent, published only on «Ha», free billing only, once, salary never invented."""
import json

import pytest

from app.agents.tools import TOOLS, Ctx, execute, tools_for
from app.models import Vacancy
from app.rbac import Scope
from app.services import hh_post

OWNER = Scope("tg:1", "owner", None, True)
FIELDS = {"role_id": "129", "area": "tashkent", "experience": "between1And3", "employment_form": "FULL",
          "work_format": "FIELD_WORK", "work_schedule_by_days": "SIX_ON_ONE_OFF", "working_hours": "HOURS_9",
          "salary_from": 8_000_000, "salary_to": 12_000_000}


class R:
    def __init__(self, code=200, data=None, headers=None):
        self.status_code, self._data, self.headers, self.content = code, data or {}, headers or {}, b"x"
        self.text = json.dumps(self._data)

    def json(self):
        return self._data

    def raise_for_status(self):
        pass


@pytest.fixture
def hh_live(monkeypatch, tmp_path):
    f = tmp_path / "hh_token.json"
    f.write_text('{"access_token": "x", "expires_at": 9999999999}')
    monkeypatch.delenv("HH_DEMO", raising=False)
    monkeypatch.setenv("HH_TOKEN_FILE", str(f))
    state = {"free": 1, "posted": []}

    def get(url, params=None, **kw):
        if url.endswith("/professional_roles"):
            return R(data={"categories": [{"roles": [{"id": "129", "name": "Торговый представитель"}]}]})
        if url.endswith("/me"):
            return R(data={"employer": {"id": "13028635", "manager_id": "16875995"}})
        if url.endswith("/available_types"):
            return R(data={"items": [{"vacancy_billing_type": {"id": "free"}, "available_publications_count": state["free"]},
                                     {"vacancy_billing_type": {"id": "standard"}, "available_publications_count": 50}]})
        raise AssertionError(url)

    def post(url, params=None, json=None, **kw):
        state["posted"].append(json)
        return R(201, {"id": "140000001"})

    monkeypatch.setattr(hh_post.httpx, "get", get)
    monkeypatch.setattr(hh_post.httpx, "post", post)
    monkeypatch.setattr("app.services.vacancies._llm", lambda *a, **k: dict(FIELDS))
    hh_post.roles.cache_clear()
    hh_post.PENDING.clear()
    hh_post.CARDS.clear()
    yield state
    hh_post.roles.cache_clear()


def _vac(db, salary="8–12 mln so'm"):
    v = Vacancy(title="Savdo agenti", salary_text=salary, schedule_text="6/1, 9:00–18:00", intro="Jamoaga agent kerak.",
                duties="Do'konlarni aylanish\nBuyurtma olish", requirements="1 yil tajriba", benefits="Rasmiy ish")
    db.add(v)
    db.commit()
    return v


def test_tool_prepares_card_publish_on_ha_only_free_once(db, hh_live):
    v = _vac(db)
    out = json.loads(execute(Ctx(db, OWNER, "hr"), TOOLS["hh_vacancy_post"], {"vacancy_id": v.id}))
    assert out["free_publications_left"] == 1 and not hh_live["posted"]  # nothing is published by the agent
    assert hh_post.CARDS["tg:1"] == v.id
    b = hh_post.PENDING[v.id]
    assert b["billing_type"] == {"id": "free"} and b["salary_range"]["from"] == 8_000_000
    assert "<li>Buyurtma olish</li>" in b["description"]
    assert hh_post.publish(db, OWNER, v) == "140000001"
    assert v.published["hh"] == "140000001" and len(hh_live["posted"]) == 1
    assert hh_post.publish(db, OWNER, v) == "140000001" and len(hh_live["posted"]) == 1  # never twice
    assert "error" in json.loads(execute(Ctx(db, OWNER, "hr"), TOOLS["hh_vacancy_post"], {"vacancy_id": v.id}))


def test_no_free_publication_no_salary_invented_stale_card(db, hh_live):
    v = _vac(db, salary="kelishiladi")
    p = hh_post.prepare(v, "tg:1")
    assert "salary_range" not in p["body"]  # HR gave no number -> no salary on hh
    hh_live["free"] = 0
    with pytest.raises(ValueError):
        hh_post.publish(db, OWNER, v)
    with pytest.raises(ValueError):
        hh_post.prepare(v, "tg:1")
    hh_post.PENDING.clear()
    hh_live["free"] = 1
    with pytest.raises(ValueError):  # after a restart the card is stale: re-create, never publish blindly
        hh_post.publish(db, OWNER, v)
    assert not hh_live["posted"]


def test_tool_writes_a_new_vacancy_from_brief(db, hh_live, monkeypatch):
    from app.services import vacancies
    monkeypatch.setattr(vacancies, "from_brief", lambda db, scope, brief: _vac(db))
    old = _vac(db)
    out = json.loads(execute(Ctx(db, OWNER, "hr"), TOOLS["hh_vacancy_post"], {"brief": "Toshkentda savdo agenti"}))
    assert out["vacancy_id"] != old.id and hh_post.CARDS["tg:1"] == out["vacancy_id"]
    assert "error" in json.loads(execute(Ctx(db, OWNER, "hr"), TOOLS["hh_vacancy_post"], {}))


def test_tool_needs_hr_head(db, hh_live):
    v = _vac(db)
    mgr = Scope("tg:5", "manager", None, False)
    assert "hh_vacancy_post" not in [t.name for t in tools_for(["hh_vacancy_post"], mgr)]
    out = json.loads(execute(Ctx(db, mgr, "hr"), TOOLS["hh_vacancy_post"], {"vacancy_id": v.id}))
    assert "error" in out and not hh_post.PENDING


def test_publish_shortcut_only_short_and_never_for_hh():
    from app.bots.main import HH_WORD, _publish_word
    assert _publish_word("joyla") and _publish_word("e'lon qil")
    assert not _publish_word("toshkentda savdo agenti uchun vakansiya joylab ber: maosh 8-12 mln, 6/1")  # a new brief
    assert HH_WORD.search("hh.uz ga joyla") and HH_WORD.search("headhunterga post joylolisinmi?")
    assert not HH_WORD.search("shhh joyla")
