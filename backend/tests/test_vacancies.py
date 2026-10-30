"""Vacancy flow: agent draft (faked LLM), edit, rewrite with comment, versions, publish once, public feed, deep link."""
from fastapi.testclient import TestClient

from app.bots.main import VACANCY_INTENT
from app.main import app
from app.services import vacancies

c = TestClient(app)


def _login(u, p):
    r = c.post("/api/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_intent_needs_noun_and_verb():
    assert VACANCY_INTENT.search("kassir uchun vakansiya yoz")
    assert VACANCY_INTENT.search("составь вакансию бухгалтера")
    assert not VACANCY_INTENT.search("ochiq vakansiyalar qancha?")
    assert not VACANCY_INTENT.search("сколько открытых вакансий")


def test_agent_draft_edit_rewrite_publish(monkeypatch):
    calls = []

    def fake_llm(system, prompt):
        calls.append(prompt)
        base = {"title": "Kassir", "branch_hint": "", "salary_text": "", "schedule_text": "6/1, 09:00–18:00",
                "intro": "Do'stona jamoa. Tel +998 90 123 45 67", "duties": ["Kassada ishlash", "Mijozlarga xizmat"],
                "requirements": ["Kamida 1 yil tajriba", "Yoshi 25 dan oshmagan"], "benefits": ["Rasmiy ishga joylashish"]}
        if len(calls) > 1:  # rewrite: HR gave a salary in the comment
            base["salary_text"] = "5 000 000 so'm"
        return base

    monkeypatch.setattr(vacancies, "_llm", fake_llm)
    h = _login("hr", "demo12345")
    v = c.post("/api/vacancies/ai", headers=h, json={"brief": "kassir kerak, 6/1"}).json()
    assert v["title"] == "Kassir" and v["status"] == "draft"
    # phone from the agent's text stripped (only the config HR phone may appear), age requirement dropped
    assert "123 45 67" not in v["ad_text"] and "Yoshi" not in v["ad_text"]
    assert "suhbatda kelishiladi" in v["ad_text"] and "salary_text" in v["missing"] and "branch" in v["missing"]
    assert c.post(f"/api/vacancies/{v['id']}/publish", headers=h, json={}).status_code == 400  # missing fields
    branch = c.get("/api/dictionaries", headers=h).json()["branches"][0]["id"]
    v = c.patch(f"/api/vacancies/{v['id']}", headers=h, json={"branch_id": branch}).json()
    v = c.post(f"/api/vacancies/{v['id']}/rewrite", headers=h, json={"comment": "maosh 5 mln"}).json()
    assert v["salary_text"] == "5 000 000 so'm" and not v["missing"] and len(v["revisions"]) == 3
    v = c.post(f"/api/vacancies/{v['id']}/publish", headers=h, json={"web": True}).json()
    assert v["status"] == "open" and v["public"] and set(v["published"]) == {"bot", "web"}
    again = c.post(f"/api/vacancies/{v['id']}/publish", headers=h, json={"web": True}).json()
    assert again["published"] == v["published"]  # never published twice
    jobs = c.get("/api/public/jobs").json()["jobs"]  # no login
    j = next(x for x in jobs if x["id"] == v["id"])
    assert j["apply_url"].endswith(f"start=vac_{v['id']}") and "created_by" not in j
    old = v["revisions"][-1]["id"]
    v = c.post(f"/api/vacancies/{v['id']}/revert/{old}", headers=h).json()
    assert v["salary_text"] in (None, "")
    c.post(f"/api/vacancies/{v['id']}/close", headers=h)
    assert c.get(f"/api/public/jobs/{v['id']}").status_code == 404
    assert c.post("/api/vacancies/ai", headers=_login("buh", "demo12345"), json={"brief": "x kerak"}).status_code == 403


def test_guest_and_consent_words():
    from app.bots.main import CAND_RE, EMP_RE, NO_RE, YES_RE
    assert CAND_RE.search("ishga kirmoqchiman") and not EMP_RE.search("ishga kirmoqchiman")
    assert EMP_RE.search("shu yerda ishlayman") and EMP_RE.search("я сотрудник")
    assert CAND_RE.search("хочу устроиться на работу")
    assert YES_RE.search("ha") and YES_RE.search("да") and not YES_RE.search("hali bilmayman")
    assert NO_RE.search("yo'q") and NO_RE.search("нет")
