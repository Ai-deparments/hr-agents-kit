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

# "+998 90 123 45 67", "(90) 123-45-67", "901234567" — but not money like "4 200 000"
PHONE_RE = re.compile(r"\+\d{1,3}[\s\-()]*\d(?:[\s\-()]*\d){7,}"
                      r"|\(?\b\d{2,3}\)?[\s\-]\d{3}[\s\-]\d{2}[\s\-]\d{2}\b"
                      r"|\b\d{9,12}\b")


def missing_fields(v: dict) -> list[str]:
    return [f for f in cfg("recruiting.required_vacancy_fields", []) if not v.get(f)]


URL_RE = re.compile(r"https?://\S+|t\.me/\S+|@\w{4,}")


def _clean(text: str | None) -> list[str]:
    """Free text written by the agent or HR: no phones, links or @handles (contacts come only from config)."""
    out = []
    for line in (text or "").splitlines():
        line = URL_RE.sub("", PHONE_RE.sub("", line)).strip(" •-–*\t")
        if line:
            out.append(line)
    return out


def apply_url(v: Vacancy) -> str | None:
    bot = (cfg("company.recruiter_bot") or "").lstrip("@")
    return f"https://t.me/{bot}?start=vac_{v.id}" if bot and v.id else None


def render_ad(v: Vacancy) -> str:
    """Fixed template (hr-vacancy-writer): code fills it, the agent only supplies field values.
    Salary is copied as given, never invented; contacts only from company config."""
    c = cfg("company", {})
    lines = [f"📢 {c.get('name', '')} jamoasiga {v.title} kerak!".replace("  ", " ").strip()]
    if intro := " ".join(_clean(v.intro)):
        lines += ["", intro]
    lines.append("")
    if v.branch:
        lines.append(f"📍 {v.branch.name}" + (f", {v.branch.city}" if v.branch.city and v.branch.city not in v.branch.name else ""))
    if v.schedule_text:
        lines.append(f"🕒 Ish vaqti: {v.schedule_text}")
    lines.append(f"💰 Maosh: {v.salary_text or 'suhbatda kelishiladi'}")
    for head, field in (("✅ Vazifalar:", v.duties), ("📌 Talablar:", v.requirements), ("🎁 Biz taklif qilamiz:", v.benefits)):
        items = _clean(field)
        if items:
            lines += ["", head] + [f"• {x}" for x in items]
    contacts = [x for x in (c.get("hr_phone"), c.get("apply_form_url")) if x]
    if contacts:
        lines += ["", "☎️ " + " | ".join(contacts)]
    if url := apply_url(v):
        lines += ["", f"👉 Ariza topshirish: {url}"]
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
    if not v.ad_custom:  # a chosen / edited ad text (checked by ad_check) is kept as is
        v.ad_text = render_ad(v)
    audit(db, scope, "vacancy_open", f"vacancy:{v.id}")
    return v


BANNED_PATTERNS = [
    r"\bhow old\b", r"\bmarri", r"\bwife\b|\bhusband\b", r"\bkids?\b",
    r"сколько\s+(вам|тебе)\s+лет", r"\bлет\s+вам\b", r"\bвозраст", r"замуж", r"жена[тт]", r"\bсупруг",
    r"\byosh(ingiz|ing)\b", r"necha\s+yosh", r"turmush", r"uylang", r"erga\s+chiq",
    # requirements in job posts: age / gender limits ("yoshi 25 dan oshmagan", "до 30 лет", "faqat erkaklar")
    r"\byoshi\b", r"\d{2}\s*(yosh|ёш)", r"\d{2}\s*(лет|years)", r"\bвозраст\w*", r"\bage\b",
    r"\b(faqat\s+)?(erkak|ayol|qiz)(lar)?\b", r"\b(только\s+)?(мужчин|женщин|девушк)\w*", r"\b(male|female)\b",
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
    if status == "hired":  # appears in Onboarding as "waiting"; HR starts the card + plan with one click
        from ..models import Employee, OnboardingHandoff
        linked = cand.telegram_id and db.scalar(select(Employee.id).where(Employee.telegram_id == cand.telegram_id))
        if not linked and not db.scalar(select(OnboardingHandoff.id).where(OnboardingHandoff.candidate_id == cand.id)):
            db.add(OnboardingHandoff(candidate_id=cand.id))
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
