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
