"""Vacancy studio: ad checker, company facts, 2 variants, pick in words, checked edits, confirm-word publish, agent tasks."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agents.tools import TOOLS, Ctx
from app.main import app
from app.models import AgentJob, AuditLog, Branch, Vacancy
from app.rbac import Scope
from app.services import ad_check, recruiting, vacancies

c = TestClient(app)
HR = Scope("tg:9999", "owner", None, True)
ADMIN = Scope("user:admin", "admin", None, True, None, {"*"})
SRC = ["Cashier", "4 200 000 UZS", "6/1, 09:00-18:00", "2 years of experience in retail", "Demo Pharmacy"]


def _h(u, p="demo12345"):
    return {"Authorization": f"Bearer {c.post('/api/auth/login', json={'username': u, 'password': p}).json()['token']}"}


def _draft(db, title="Studio cashier", salary="4 200 000 UZS") -> Vacancy:
    b = db.scalar(select(Branch).where(Branch.code == "P02"))
    v = Vacancy(title=title, branch_id=b.id, position_code="cashier", salary_text=salary, schedule_text="6/1, 09:00-18:00",
                requirements="2 years of experience in retail", status="draft")
    db.add(v)
    db.flush()
    v.ad_text = recruiting.render_ad(v)
    return v


@pytest.mark.parametrize("text", [
    "Cashier wanted. Salary 4 200 000 UZS, attractive salary and a friendly team.",
    "We need 2 years of experience. Schedule 6/1, 09:00-18:00. Age 18+.",
    "Опыт от 2 лет. Kassir kerak, karyera o'sishi bor.",
])
def test_checker_no_false_positives(text):
    r = ad_check.check_ad(text, SRC)
    assert r["ok"], r["problems"]


@pytest.mark.parametrize("text,kind", [
    ("Cashier, 20-35 yosh", "age"),
    ("Возраст от 25", "age"),
    ("Only women, please", "gender"),
    ("Только девушки", "gender"),
    ("Приятная внешность обязательна", "appearance"),
    ("Slavic nationality", "nationality"),
    ("Muslim candidates preferred", "religion"),
    ("Salary 9 000 000 UZS", "numbers"),
])
def test_checker_rejects(text, kind):
    r = ad_check.check_ad(text, SRC)
    assert not r["ok"] and any(p.startswith(kind) for p in r["problems"]), r


def test_checker_cuts_phones_and_links_keeps_config_contacts_and_money():
    contact = ad_check.contacts()
    r = ad_check.check_ad("Cashier, 4 200 000 UZS. Call +998 90 123 45 67 or https://example.org and @someone_else. "
                          + " | ".join(contact), SRC)
    assert "+998 90 123 45 67" not in r["text"] and "example.org" not in r["text"] and "@someone_else" not in r["text"]
    assert "4 200 000" in r["text"] and all(ct in r["text"] for ct in contact) and len(r["removed"]) == 3
    assert not recruiting.PHONE_RE.search("Maosh 4 200 000 so'm")  # money is not a phone


def test_company_facts_admin_only_audited_and_used_as_source(db):
    assert c.patch("/api/company-facts", json={"text": "x"}, headers=_h("recruiter")).status_code == 403
    r = c.patch("/api/company-facts", json={"text": "Free lunch. Uniform provided. 13th salary."}, headers=_h("admin", "admin12345"))
    assert r.status_code == 200
    got = c.get("/api/company-facts", headers=_h("recruiter")).json()
    assert got["text"].startswith("Free lunch") and got["can_edit"] is False
    log = db.scalar(select(AuditLog).where(AuditLog.action == "company_facts_update").order_by(AuditLog.id.desc()))
    assert "Free lunch" not in str(log.details)  # texts logged as lengths
    v = _draft(db)
    assert vacancies.check(db, v, "Cashier. Bonus: 13th salary.")["ok"]  # the number comes from the facts
    db.rollback()


def test_variants_fallback_choose_and_template_reset(db, monkeypatch):
    v = _draft(db)
    monkeypatch.setattr(vacancies, "_ask", lambda task, payload, n: ["Only women. Salary 9 999 999", "Studio cashier, 4 200 000 UZS, 6/1."])
    a, b = vacancies.make_variants(db, HR, v)
    assert (a.source, b.source) == ("template", "agent")  # a text that breaks the rules never reaches HR
    assert recruiting.apply_url(v) in b.text  # code adds the apply link
    vacancies.choose(db, HR, v, 2)
    assert v.ad_custom and v.ad_text == b.text
    vacancies.update(db, HR, v, {"salary_text": "5 000 000 UZS"})  # the card changed -> back to the template
    assert not v.ad_custom and "5 000 000" in v.ad_text and vacancies.variants(db, v) == []
    db.rollback()


def test_offline_variants_are_templates(db):
    v = _draft(db)
    vs = vacancies.make_variants(db, HR, v)
    assert [x.source for x in vs] == ["template", "template"] and all(vacancies.check(db, v, x.text)["ok"] for x in vs)
    db.rollback()


@pytest.mark.parametrize("text,n", [("1", 1), ("2-variant", 2), ("ikkinchisini ol", 2), ("второй вариант", 2),
                                    ("the first one", 1), ("birinchisi", 1), ("2 ta variant yoz", None),
                                    ("maoshni 2 mln qil", None), ("1 yil tajriba qo'sh", None)])
def test_pick_variant_in_words(text, n):
    assert vacancies.pick_variant(text) == n


def test_pick_variant_model_may_only_label(monkeypatch):
    monkeypatch.setattr(vacancies, "_llm", lambda s, p, schema=None: {"pick": 2})
    assert vacancies.pick_variant_ai("menga qisqasi yoqdi") == 2
    monkeypatch.setattr(vacancies, "_llm", lambda s, p, schema=None: {"pick": 7})
    assert vacancies.pick_variant_ai("…") is None


def test_confirm_word_publish_only(db):
    v = _draft(db)
    db.commit()
    assert vacancies.is_confirm("E'lon qil!") and vacancies.is_confirm(f"опубликуй {v.id}")
    assert not vacancies.is_confirm("e'lon qilma") and not vacancies.is_confirm("не опубликуй") and not vacancies.is_confirm("")
    tool = TOOLS["vacancy_publish"].fn
    assert "error" in tool(Ctx(db, HR, "hr", user_text="hali e'lon qilma"), vacancy_id=v.id)
    assert db.get(Vacancy, v.id).status == "draft"
    assert tool(Ctx(db, HR, "hr", user_text="e'lon qil"), vacancy_id=v.id)["published"]
    assert db.get(Vacancy, v.id).status == "open"


def test_custom_text_kept_on_publish_and_rechecked(db):
    v = _draft(db, title="Custom text cashier")
    vacancies.set_ad(db, HR, v, "Custom text cashier. 4 200 000 UZS, 6/1.")
    vacancies.publish(db, HR, v, web=True)
    assert v.status == "open" and v.ad_text.startswith("Custom text cashier") and v.ad_custom
    with pytest.raises(ValueError):
        vacancies.set_ad(db, HR, v, "Only men. Salary 7 000 000")
    db.rollback()


def test_agent_job_queue_worker_and_human_apply(db, monkeypatch):
    v = _draft(db, title="Job cashier")
    before = v.ad_text
    db.commit()
    j = vacancies.queue_job(db, HR, v, "make it shorter")
    db.commit()
    assert vacancies.run_jobs(db) >= 1
    db.refresh(j)
    assert j.status == "failed" and "AI is off" in j.error  # offline: nothing invented
    monkeypatch.setattr(vacancies, "_ask", lambda task, payload, n: ["Job cashier at Demo Pharmacy. 4 200 000 UZS, 6/1."])
    j2 = vacancies.queue_job(db, HR, v, "shorter please")
    db.commit()
    vacancies.run_jobs(db)
    db.refresh(j2)
    db.refresh(v)
    assert j2.status == "done" and v.ad_text == before  # nothing changes until a person applies it
    vacancies.apply_job(db, HR, j2)
    assert v.ad_text.startswith("Job cashier at") and j2.status == "applied"
    assert vacancies.run_jobs(db) == 0  # a job never runs twice
    db.commit()


def test_panel_studio_endpoints(db, monkeypatch):
    h = _h("recruiter")
    v = _draft(db, title="Panel studio cashier")
    db.commit()
    s = c.post(f"/api/vacancies/{v.id}/variants", headers=h).json()
    assert len(s["variants"]) == 2
    assert c.post(f"/api/vacancies/{v.id}/variants/1/choose", headers=h).json()["ad_custom"] is True
    bad = c.patch(f"/api/vacancies/{v.id}/ad", json={"text": "Only women, 4 200 000 UZS"}, headers=h)
    assert bad.status_code == 400 and "gender" in bad.json()["detail"]
    chk = c.post(f"/api/vacancies/{v.id}/ad/check", json={"text": "Call +998901234567 now"}, headers=h).json()
    assert chk["removed"] and "+998901234567" not in chk["text"]
    j = c.post(f"/api/vacancies/{v.id}/jobs", json={"instruction": "add the schedule first"}, headers=h).json()
    assert j["jobs"][0]["status"] == "queued"
    t = c.post(f"/api/vacancies/{v.id}/ad/template", headers=h).json()
    assert t["ad_custom"] is False
    assert c.post(f"/api/vacancies/{v.id}/variants", headers=_h("buh")).status_code == 403
    assert db.scalar(select(AgentJob).where(AgentJob.vacancy_id == v.id)) is not None


def test_channel_post_has_no_inline_button(db, monkeypatch):
    v = _draft(db, title="Channel cashier")
    sent = {}

    class R:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True, "result": {"message_id": 5}}

    monkeypatch.setattr(vacancies.httpx, "post", lambda url, json, timeout: sent.update(json) or R())
    monkeypatch.setenv("BOT_TOKEN_HUB", "x")
    monkeypatch.setattr(vacancies, "cfg", lambda k, d=None: "@jobs_demo" if k == "recruiting.jobs_channel" else recruiting.cfg(k, d))
    vacancies._post_channel(v)
    assert "reply_markup" not in sent and "start=vac_" in sent["text"]
    db.rollback()


def test_bot_reply_picks_then_rewrites_checked_text(db, monkeypatch):
    from app.bots import main as bot
    v = _draft(db, title="Bot studio cashier")
    db.commit()
    vacancies.make_variants(db, HR, v)
    db.commit()
    assert bot._has_variants_pick(v.id, "ikkinchisi") and not bot._has_variants_pick(v.id, "maosh 5 mln")
    assert bot._vacancy_reply(9999, v.id, "2") == ("picked", None)
    db.expire_all()
    assert db.get(Vacancy, v.id).ad_custom
    monkeypatch.setattr(vacancies, "_ask", lambda task, payload, n: ["Only girls. Bot studio cashier."])
    kind, err = bot._vacancy_reply(9999, v.id, "qisqaroq qil")
    assert kind == "rewritten" and "gender" in err  # the rewrite broke a rule -> nothing saved
    monkeypatch.setattr(vacancies, "_ask", lambda task, payload, n: ["Bot studio cashier. 4 200 000 UZS."])
    assert bot._vacancy_reply(9999, v.id, "qisqaroq qil") == ("rewritten", None)
    db.expire_all()
    assert db.get(Vacancy, v.id).ad_text.startswith("Bot studio cashier. 4 200 000")


def test_revert_brings_back_a_chosen_text(db):
    from app.models import VacancyRevision
    v = _draft(db, title="Revert cashier")
    vacancies.set_ad(db, HR, v, "Revert cashier. 4 200 000 UZS.", "variant 1")
    rev = db.scalar(select(VacancyRevision).where(VacancyRevision.vacancy_id == v.id).order_by(VacancyRevision.id.desc()))
    vacancies.use_template(db, HR, v)
    assert not v.ad_custom
    vacancies.revert(db, HR, v, rev)
    assert v.ad_custom and v.ad_text.startswith("Revert cashier. 4 200 000")
    db.rollback()
