"""Lateness alert rule: when an employee is late N times in a month (then 2N, 3N…), the owner (and optionally HR)
gets a private Telegram message. Set by HR in words to the agent or in the panel ("Davomat"). Off by default.
On enabling, people already over the limit are not re-announced: counting starts from that moment."""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Setting
from ..rbac import Scope
from . import attendance as att

KEY = "discipline_alerts"
SYSTEM = Scope("system", "owner", None, True)
DEFAULT = {"enabled": False, "late_count": 3, "to": "owner"}  # to: owner | owner_hr


def get(db: Session) -> dict:
    s = db.get(Setting, KEY)
    v = dict(s.value) if s else {}
    return {**DEFAULT, **{k: v[k] for k in DEFAULT if k in v}}


def _store(db: Session, v: dict) -> None:
    s = db.get(Setting, KEY) or Setting(key=KEY, value={})
    s.value = v
    db.merge(s)


def _late_counts(db: Session, month: str) -> dict[int, tuple[str, int]]:
    t = att.month_tabel(db, SYSTEM, month)
    return {r["employee_id"]: (r["full_name"], r["late_days"]) for r in t["rows"]}


def save(db: Session, enabled: bool, late_count: int, to: str = "owner", today: date | None = None) -> dict:
    today = today or date.today()
    s = db.get(Setting, KEY)
    v = dict(s.value) if s else {}
    was_on = v.get("enabled", False)
    v.update(enabled=bool(enabled), late_count=max(1, min(int(late_count), 31)), to=to if to in ("owner", "owner_hr") else "owner")
    if enabled and (not was_on or v.get("baseline_month") != today.strftime("%Y-%m")):
        # start counting now: current levels are known, only new crossings will be sent
        month = today.strftime("%Y-%m")
        n = v["late_count"]
        v["baseline_month"] = month
        v["sent"] = {str(eid): late // n for eid, (_, late) in _late_counts(db, month).items()}
    _store(db, v)
    return get(db)


def over_limit(db: Session, today: date | None = None) -> list[dict]:
    today = today or date.today()
    n = get(db)["late_count"]
    return sorted(({"employee_id": e, "full_name": name, "late_days": late}
                   for e, (name, late) in _late_counts(db, today.strftime("%Y-%m")).items() if late >= n),
                  key=lambda x: -x["late_days"])


def check(db: Session, today: date | None = None) -> list[tuple[int, str]]:
    """New crossings of N, 2N, 3N… this month -> [(telegram_id, text)]. Records what was sent."""
    today = today or date.today()
    s = db.get(Setting, KEY)
    v = dict(s.value) if s else {}
    if not v.get("enabled"):
        return []
    month, n = today.strftime("%Y-%m"), int(v.get("late_count", 3))
    if v.get("baseline_month") != month:  # a new month starts from zero
        v["baseline_month"], v["sent"] = month, {}
    sent = dict(v.get("sent") or {})
    cfg = settings()
    to = sorted(cfg.owner_ids | (cfg.hr_head_ids if v.get("to") == "owner_hr" else set()))
    out = []
    for eid, (name, late) in _late_counts(db, month).items():
        level = late // n
        if level > int(sent.get(str(eid), 0)):
            sent[str(eid)] = level
            text = (f"⚠️ {name} bu oy {late}-marta kech qoldi (chegara: {n}).\n"
                    f"Batafsil: agentdan «{name} bu oy qachon kech qoldi?» deb so'rang.")
            out += [(i, text) for i in to]
    v["sent"] = sent
    _store(db, v)
    return out
