"""Reports into a forum group: the bot learns topic names from messages in each topic and sends every report
kind into the topic whose name fits it (davomat, vakansiya, onboarding…); anything else -> the default reports topic."""
from __future__ import annotations

import os
import re

from sqlalchemy.orm import Session

from ..models import Setting

KEY = "report_topics"
KINDS = {
    "attendance": r"(davomat|kechik|tabel|boshli|посещ|опозд|табел|начальник|attendance)",
    "analytics": r"(analit|аналит|tahlil)",
    "recruiting": r"(vakans|nomzod|rekrut|yollash|ваканс|кандидат|найм|подбор|recruit|hh)",
    "onboarding": r"(onboard|adapt|адапт|o'?qit|обучен|yangi xodim|новичк)",
    "documents": r"(hujjat|документ|doc)",
    "payroll": r"(oylik|maosh|зарплат|payroll|kpi|бонус)",
    "digest": r"(boshli|начальник|hisobot|отч[её]т|report|ceo|digest|haftalik|недел)",
}


def _get(db: Session) -> dict:
    s = db.get(Setting, KEY)
    return dict(s.value) if s else {}


def learn(db: Session, chat_id: int, thread_id: int, name: str) -> bool:
    """Remember a topic name. Returns True when something changed."""
    v = _get(db)
    topics = dict(v.get("topics", {}))
    if v.get("chat_id") == chat_id and topics.get(str(thread_id)) == name:
        return False
    topics[str(thread_id)] = name[:128]
    v.update(chat_id=chat_id, topics=topics)
    s = db.get(Setting, KEY) or Setting(key=KEY)
    s.value = v
    db.merge(s)
    return True


def default_thread() -> int | None:
    t = os.getenv("REPORT_THREAD_ID")
    return int(t) if t and t.isdigit() else None


def thread_for(db: Session, kind: str) -> int | None:
    """Explicit map (panel) -> topic name match -> default reports topic."""
    v = _get(db)
    if (m := v.get("map", {}).get(kind)) is not None:
        return int(m)
    pat = KINDS.get(kind)
    if pat:
        for tid, name in sorted(v.get("topics", {}).items(), key=lambda x: int(x[0])):
            if re.search(pat, name.lower()):
                return int(tid)
    return default_thread()


def overview(db: Session) -> dict:
    v = _get(db)
    return {"chat_id": v.get("chat_id"), "topics": v.get("topics", {}),
            "routes": {k: thread_for(db, k) for k in KINDS}, "default": default_thread()}
