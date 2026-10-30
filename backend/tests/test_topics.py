"""Reports go into the forum topic whose name fits the report kind; unknown -> default reports topic."""
from app.services import topics


def test_routes_by_topic_name(db, monkeypatch):
    monkeypatch.setenv("REPORT_THREAD_ID", "6")
    assert topics.thread_for(db, "attendance") == 6                     # nothing learned yet -> default
    topics.learn(db, -1001234567890, 2, "Davomat")
    topics.learn(db, -1001234567890, 4, "Вакансии и кандидаты")
    topics.learn(db, -1001234567890, 8, "Onboarding")
    db.commit()
    assert topics.thread_for(db, "attendance") == 2
    assert topics.thread_for(db, "recruiting") == 4
    assert topics.thread_for(db, "onboarding") == 8
    assert topics.thread_for(db, "digest") == 6
    assert not topics.learn(db, -1001234567890, 2, "Davomat")           # unchanged -> no write


def test_group_addressing(monkeypatch):
    from types import SimpleNamespace as N
    from app.bots import main as bot
    monkeypatch.setattr(bot, "is_hr_group", lambda m: m.chat.id == -100)
    human, me = N(is_bot=False, username="ali"), N(is_bot=True, username="hrbot")
    root = N(message_id=6, from_user=human, text=None, caption=None)

    def msg(text, chat=-100, reply=None, topic=True):
        return N(chat=N(id=chat, type="supergroup"), text=text, from_user=human, is_topic_message=topic,
                 message_thread_id=6, reply_to_message=reply or root)
    assert bot._is_addressed(msg("kim kech qoldi?"), "hrbot")                       # plain message in a topic
    assert not bot._is_addressed(msg("rahmat"), "hrbot")                            # short thanks: silent
    assert not bot._is_addressed(msg("men ham", reply=N(message_id=9, from_user=human)), "hrbot")  # people talking
    assert bot._is_addressed(msg("davom et", reply=N(message_id=9, from_user=me)), "hrbot")       # reply to the bot
    assert not bot._is_addressed(msg("kim kech qoldi?", chat=-200), "hrbot")       # other groups: only on mention
    assert bot._is_addressed(msg("@hrbot kim kech qoldi?", chat=-200), "hrbot")


def test_visibility_group_vs_private(db, monkeypatch):
    """Default: everything visible. The panel can hide categories per role and per person, separately per chat."""
    from fastapi.testclient import TestClient
    from app.bots import main as bot
    from app.main import app
    c = TestClient(app)
    admin = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"username": "admin", "password": "admin12345"}).json()["token"]}
    seen = {}
    monkeypatch.setattr(bot, "run_agent", lambda db, agent, scope, text, user_key: seen.update(p=scope.payroll, h=set(scope.hidden)) or "ok")
    owner = next(iter(bot.settings().owner_ids), None) or 1
    bot._answer_sync("hr", owner, "oylik qancha?", "grp:-1:2", True)
    assert seen["p"] is True and seen["h"] == set()                     # default: group sees everything
    cfg = c.get("/api/bot-visibility", headers=admin).json()
    cfg["settings"]["people"] = {str(owner): {"name": "Owner", "group": ["attendance"], "private": list(cfg["categories"])}}
    assert c.put("/api/bot-visibility", headers=admin, json=cfg["settings"]).status_code == 200
    bot._answer_sync("hr", owner, "oylik qancha?", "grp:-1:2", True)
    assert seen["p"] is False and "payroll" in seen["h"] and "attendance" not in seen["h"]
    bot._answer_sync("hr", owner, "oylik qancha?", None, False)
    assert seen["p"] is True and seen["h"] == set()                     # private chat keeps everything
    from app.agents.registry import AGENTS
    from app.agents.tools import tools_for
    from app.rbac import Scope
    sc = Scope("tg:1", "owner", None, True, hidden={"recruiting"})
    names = {t.name for t in tools_for(AGENTS["hr"].tools, sc)}
    assert "job_offer" not in names and "attendance_day" in names
    hr = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"username": "hr", "password": "demo12345"}).json()["token"]}
    assert c.get("/api/bot-visibility", headers=hr).status_code == 403  # main admin only
