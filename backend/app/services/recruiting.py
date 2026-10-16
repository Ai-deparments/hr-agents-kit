"""Vacancies (fixed template, never invent salary/phones) + interview scoring (4 criteria).
No auto-reject: hire / reject is set by a person only."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import cfg
from ..models import Candidate, Vacancy
from ..rbac import Scope, audit

BANNED_TOPICS = ("age", "gender", "nationality", "religion", "marital", "children", "pregnan", "appearance",
                 "возраст", "национальн", "религи", "замуж", "женат", "дети", "беремен", "внешн",
                 "yoshingiz", "millat", "diningiz", "turmush", "farzand", "homilador")

PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{7,}\d")


def missing_fields(v: dict) -> list[str]:
    return [f for f in cfg("recruiting.required_vacancy_fields", []) if not v.get(f)]


def render_ad(v: Vacancy) -> str:
    """Fixed template. Only the HR phone from config is allowed — any other phone is stripped."""
    c = cfg("company", {})
    req = PHONE_RE.sub("", v.requirements or "").strip()
    lines = [f"📢 {c.get('name', '')} — {c.get('description', '')}", "", f"💼 {v.title}"]
    if v.branch:
        lines.append(f"📍 {v.branch.name}" + (f", {v.branch.city}" if v.branch.city else ""))
    if v.schedule_text:
        lines.append(f"🕒 {v.schedule_text}")
    if v.salary_text:
        lines.append(f"💰 {v.salary_text}")
    if req:
        lines += ["", "Requirements:", req]
    contacts = [x for x in (c.get("hr_phone"), c.get("recruiter_bot"), c.get("apply_form_url")) if x]
    if contacts:
        lines += ["", "☎️ " + " | ".join(contacts)]
    return "\n".join(lines)


def open_vacancy(db: Session, scope: Scope, v: Vacancy) -> Vacancy:
    miss = missing_fields({"title": v.title, "branch": v.branch_id, "salary_text": v.salary_text, "schedule_text": v.schedule_text})
    if miss:
        raise ValueError("Missing fields: " + ", ".join(miss))
    if v.status == "open":
        return v  # never published twice
    sla = cfg("recruiting.sla_days_by_position", {}) or {}
    v.sla_days = int(sla.get(v.position_code, cfg("recruiting.sla_days_default", 21)))
    v.status, v.opened_at = "open", date.today()
    v.ad_text = render_ad(v)
    audit(db, scope, "vacancy_open", f"vacancy:{v.id}")
    return v


BANNED_PATTERNS = [
    r"\bhow old\b", r"\bmarri", r"\bwife\b|\bhusband\b", r"\bkids?\b",
    r"сколько\s+(вам|тебе)\s+лет", r"\bлет\s+вам\b", r"\bвозраст", r"замуж", r"жена[тт]", r"\bсупруг",
    r"\byosh(ingiz|ing)\b", r"necha\s+yosh", r"turmush", r"uylang", r"erga\s+chiq",
]


def find_banned(question: str) -> list[str]:
    q = question.lower()
    hits = [w for w in BANNED_TOPICS if re.search(r"\b" + re.escape(w), q)]
    return hits + [p for p in BANNED_PATTERNS if re.search(p, q)]


def score_candidate(breakdown: dict) -> dict:
    """breakdown = {criterion: {"score": 0..100, "comment": str}}. A criterion without a comment is ignored."""
    weights = cfg("recruiting.weights", {"role_fit": 40, "specifics": 25, "communication": 15, "motivation": 20})
    used, total_w, acc = {}, 0, 0.0
    for k, w in weights.items():
        item = breakdown.get(k) or {}
        if item.get("comment") and isinstance(item.get("score"), (int, float)):
            used[k] = item
            total_w += w
            acc += w * max(0, min(100, item["score"]))
    if not total_w:
        return {"score": None, "label": None, "status": "new", "note": "evaluate manually"}
    score = round(acc / total_w)
    label = "strong" if score >= 80 else "medium" if score >= 60 else "weak"
    status = "shortlist" if score >= int(cfg("recruiting.shortlist_threshold", 70)) else "new"
    return {"score": score, "label": label, "status": status, "used": list(used)}


def apply_score(db: Session, cand: Candidate, breakdown: dict) -> Candidate:
    res = score_candidate(breakdown)
    cand.breakdown, cand.score, cand.label = breakdown, res["score"], res["label"]
    if cand.status in (None, "new"):  # None = not flushed yet (column default not applied)
        cand.status = res["status"]  # only new -> shortlist; never hired/rejected
    return cand


def set_status(db: Session, scope: Scope, cand: Candidate, status: str) -> Candidate:
    if status in ("hired", "rejected") and scope.actor.startswith("agent:"):
        raise PermissionError("Only a person hires or rejects")
    if status not in ("new", "shortlist", "hired", "rejected"):
        raise ValueError("Bad status")
    cand.status = status
    if status in ("hired", "rejected"):
        cand.decided_at = datetime.now()
    audit(db, scope, "candidate_status", f"candidate:{cand.id}", status=status)
    return cand


def purge_candidates(db: Session, today: datetime | None = None) -> int:
    """Personal-data retention: anonymise rejected candidates (and stale 'new' ones) after recruiting.retention_days.
    Funnel statistics survive; names, phones and answers do not."""
    days = int(cfg("recruiting.retention_days", 180))
    limit = (today or datetime.now()) - timedelta(days=days)
    n = 0
    for c in db.scalars(select(Candidate).where(Candidate.full_name != "—")):
        decided = c.decided_at or (c.created_at if c.status == "new" else None)
        if c.status in ("rejected", "new") and decided and decided < limit:
            c.full_name, c.phone, c.telegram_id, c.answers, c.breakdown = "—", None, None, [], {}
            n += 1
    if n:
        audit(db, None, "candidates_purged", None, count=n, retention_days=days)
    return n
