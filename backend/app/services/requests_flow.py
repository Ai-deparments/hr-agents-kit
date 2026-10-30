"""Employee requests in words: a short notice goes to HR, HR answers «tasdiqlayman» / «rad: sabab» (reply to the
notice or "so'rov 12 ..."), the employee gets the answer — and the PDF for a certificate; a vacation order goes
to the HR group for signature. Only HR decides (request_approve is human-only)."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import ROOT, settings
from ..models import DocTemplate, Employee, LeaveRequest, Outbox
from ..rbac import Scope
from . import docgen, people
from .people import AccessDenied

log = logging.getLogger("requests_flow")

KIND_UZ = {"vacation": "ta'til", "certificate": "ma'lumotnoma", "shift_swap": "smena almashish",
           "sick_leave": "kasallik varaqasi", "other": "boshqa so'rov"}
KIND_RU = {"vacation": "отпуск", "certificate": "справка", "shift_swap": "обмен сменами",
           "sick_leave": "больничный", "other": "заявка"}
NOTICE_RE = re.compile(r"So'rov #(\d{1,9})")
# "so'rov 12 ...", "заявка №12 ...", "#12 ..." at the start of the message
CMD_RE = re.compile(r"^\s*(?:(?:so['ʻ’`]?rov|заявк[аиу]?)\s*[#№]?\s*|#)(\d{1,9})\b", re.I)
_W = r"(?<![\w'ʻ’])({})(?![\w'ʻ’])"
# a decision must START the message ("tasdiqlayman", "rad: sabab"); a word somewhere inside ("bilmayman, ok keyin")
# is not a decision. Short words count only as the whole message.
APPROVE_RE = re.compile(r"\s*(tasdiq\w*|одобр\w*|согласов\w*|approve\w*)(?![\w'ʻ’])", re.I)
REJECT_RE = re.compile(r"\s*(rad\w*|отказ\w*|reject\w*)(?![\w'ʻ’])", re.I)
SHORT_YES = re.compile(r"\s*(ha|ok|ок|да|xo['ʻ’]?p)[\s.!]*$", re.I)
SHORT_NO = re.compile(r"\s*(yo['ʻ’]?q|нет)(?![\w'ʻ’])", re.I)


def docs_dir() -> Path:
    return ROOT / "data" / "uploads" / "docs"


def _hr_targets() -> list[tuple[int, str | None]]:
    """The HR group topic when configured, else every owner / HR head privately."""
    s = settings()
    if s.report_chat_id:
        return [(s.report_chat_id, "attendance")]
    return [(i, None) for i in sorted(s.owner_ids | s.hr_head_ids)]


def _period(r: LeaveRequest) -> str:
    if not r.date_from:
        return ""
    f, t = r.date_from.strftime("%d.%m"), (r.date_to or r.date_from).strftime("%d.%m")
    out = f" {f}" if f == t else f" {f}–{t}"
    return out + (f" ({r.days:g} kun)" if r.days else "")


def notice_text(r: LeaveRequest) -> str:
    note = f" · «{r.comment[:120]}»" if r.comment else ""
    return (f"📝 So'rov #{r.id} · {r.employee.full_name} — {KIND_UZ.get(r.kind, r.kind)}{_period(r)}{note}.\n"
            f"Javob: shu xabarga «tasdiqlayman» yoki «rad: sabab» deb yozing.")


def notify_created(db: Session, scope: Scope, r: LeaveRequest) -> int:
    """Queue the notice for HR. Returns how many messages were queued."""
    text = notice_text(r)
    targets = _hr_targets()
    for chat, topic in targets:
        db.add(Outbox(telegram_id=chat, text=text, topic=topic))
    return len(targets)


def parse(text: str, replied: str = "") -> tuple[int, bool, str] | None:
    """(request id, approve?, reason) when the text is a decision on a request, else None."""
    m = NOTICE_RE.search(replied or "")
    rid = int(m.group(1)) if m else None
    body = text
    if rid is None:
        c = CMD_RE.match(text)
        if not c:
            return None
        rid, body = int(c.group(1)), text[c.end():]
    a = APPROVE_RE.match(body) or SHORT_YES.match(body)
    r = None if a else (REJECT_RE.match(body) or SHORT_NO.match(body))
    if not a and not r:
        return None
    approve, hit = bool(a), a or r
    rest = body[hit.end():]
    reason = rest.split(":", 1)[1] if ":" in rest else rest
    return rid, approve, reason.strip(" .,-—")[:300]


def _pdf_file(db: Session, scope: Scope, code: str, emp: Employee, extra: dict | None = None) -> tuple[str, Path] | None:
    docgen.ensure_templates(db)
    tpl = db.scalar(select(DocTemplate).where(DocTemplate.code == code, DocTemplate.active.is_(True)))
    if not tpl:
        return None
    d = docgen.issue(db, scope, tpl, emp, extra)
    out = docs_dir()
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"{d.number}.pdf"
    f.write_bytes(docgen.pdf(d))
    return f"{d.title} · {d.number} · {emp.full_name}", f


def decide(db: Session, scope: Scope, rid: int, approve: bool, reason: str = "") -> dict:
    """HR's decision in words. Raises ValueError / AccessDenied / PermissionError like the panel does."""
    if not scope.at_least("hr_head"):
        raise AccessDenied("Only HR decides requests")
    return apply_decision(db, scope, rid, approve, reason)


def apply_decision(db: Session, scope: Scope, rid: int, approve: bool, reason: str = "") -> dict:
    """Record the decision and tell the employee (+ PDFs). The caller has already checked the right to decide
    (bot: hr_head scope; panel: the 'requests.decide' permission)."""
    reason = reason.strip() or ("tasdiqlandi" if approve else "sabab ko'rsatilmagan")
    r = people.decide_request(db, scope, rid, approve, reason)  # writes the audit entry
    emp, kind = r.employee, KIND_UZ.get(r.kind, r.kind)
    res = {"id": r.id, "status": r.status, "employee": emp.full_name, "sent": False, "doc": None, "order": None}
    per = _period(r)
    if emp.lang == "ru":  # the employee's own language (remembered from their messages to the bot)
        per = per.replace(" kun)", " дн.)")
        text = (f"✅ Ваша заявка #{r.id} ({KIND_RU.get(r.kind, r.kind)}{per}) одобрена." if approve else
                f"❌ Ваша заявка #{r.id} ({KIND_RU.get(r.kind, r.kind)}{per}) отклонена. Причина: {reason}")
    elif approve:
        text = f"✅ So'rovingiz #{r.id} ({kind}{per}) tasdiqlandi."
    else:
        text = f"❌ So'rovingiz #{r.id} ({kind}{per}) rad etildi. Sabab: {reason}"
    file = None
    if approve and r.kind == "certificate":
        try:
            got = _pdf_file(db, scope, "employment_certificate", emp)
        except (RuntimeError, OSError) as e:
            log.warning("certificate pdf #%s: %s", r.id, e)
            got = None
        if got:
            text, file = f"{text}\n{got[0]}", str(got[1])
            res["doc"] = got[1].name
    if emp.telegram_id:
        db.add(Outbox(telegram_id=emp.telegram_id, text=text, file_path=file))
        res["sent"] = True
    if approve and r.kind == "vacation" and r.date_from and r.date_to:
        extra = {"leave_from": r.date_from.strftime("%d.%m.%Y"), "leave_to": r.date_to.strftime("%d.%m.%Y"),
                 "leave_days": f"{r.days:g}" if r.days else None}
        try:
            got = _pdf_file(db, scope, "leave_order", emp, extra)
        except (RuntimeError, OSError) as e:
            log.warning("leave order pdf #%s: %s", r.id, e)
            got = None
        if got:
            s = settings()
            targets = [(s.report_chat_id, "documents")] if s.report_chat_id else _hr_targets()
            for chat, topic in targets:
                db.add(Outbox(telegram_id=chat, text=f"✍️ Imzoga: {got[0]}", file_path=str(got[1]), topic=topic))
            res["order"] = got[1].name
    return res


def handle(db: Session, scope: Scope, text: str, replied: str = "") -> dict | None:
    """A message from HR: a decision -> result dict ({"error": ...} when it failed); anything else -> None."""
    if not scope.at_least("hr_head"):
        return None
    p = parse(text, replied)
    if not p:
        return None
    rid, approve, reason = p
    try:
        res = decide(db, scope, rid, approve, reason)
    except (ValueError, AccessDenied, PermissionError) as e:
        db.rollback()
        return {"id": rid, "error": str(e)}
    db.commit()
    return res
