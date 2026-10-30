"""Onboarding materials: upload a video / method / link, send it to chosen employees through the bot,
schedule a talk on it with some of them, mark talks done."""
from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require
from ..config import ROOT
from ..db import get_db
from ..models import Employee, MaterialSend, OnboardingMaterial, Outbox
from ..rbac import Scope, audit

router = APIRouter(prefix="/api/onboarding/materials")
UPLOADS = ROOT / "data" / "uploads" / "onboarding"
MAX_FILE = 49 * 1024 * 1024  # Telegram bots send files up to 50 MB
VIDEO = {".mp4", ".mov", ".m4v", ".webm"}
DOCS = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".png", ".jpg"}


def _row(m: OnboardingMaterial, sends: list[MaterialSend] | None = None) -> dict:
    out = {"id": m.id, "title": m.title, "description": m.description, "kind": m.kind, "filename": m.filename, "url": m.url,
           "size": m.size, "created_by": m.created_by, "created_at": m.created_at, "position_ids": m.position_ids or [],
           "department_ids": m.department_ids or [], "day_offset": m.day_offset or 0, "for_new": m.for_new is not False}
    if sends is not None:
        out.update(sent=sum(1 for s in sends if s.queued), planned=sum(1 for s in sends if not s.queued),
                   viewed=sum(1 for s in sends if s.viewed_at),
                   talks=sum(1 for s in sends if s.talk_at), talks_done=sum(1 for s in sends if s.talk_done))
    return out


def _ids(raw: str) -> list[int] | None:
    out = [int(x) for x in (raw or "").replace(" ", "").split(",") if x.isdigit()]
    return out or None


@router.get("")
def materials(scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    sends: dict[int, list[MaterialSend]] = {}
    for s in db.scalars(select(MaterialSend)):
        sends.setdefault(s.material_id, []).append(s)
    return [_row(m, sends.get(m.id, [])) for m in db.scalars(select(OnboardingMaterial).order_by(OnboardingMaterial.id.desc()))]


@router.post("")
async def material_create(title: str = Form(min_length=2, max_length=200), description: str = Form(default="", max_length=2000),
                          url: str = Form(default=""), file: UploadFile | None = None,
                          position_ids: str = Form(default=""), department_ids: str = Form(default=""),
                          day_offset: int = Form(default=0, ge=0, le=60), for_new: bool = Form(default=True),
                          scope: Scope = Depends(require("onboarding")), db: Session = Depends(get_db)):
    m = OnboardingMaterial(title=title, description=description, created_by=scope.actor, position_ids=_ids(position_ids),
                           department_ids=_ids(department_ids), day_offset=day_offset, for_new=for_new)
    if file and file.filename:
        name = Path(file.filename).name
        ext = Path(name).suffix.lower()
        if ext not in VIDEO | DOCS:
            raise HTTPException(400, f"Allowed: {', '.join(sorted(VIDEO | DOCS))}")
        UPLOADS.mkdir(parents=True, exist_ok=True)
        path = UPLOADS / f"{secrets.token_hex(12)}{ext}"
        size = 0
        with open(path, "wb") as out:  # stream to disk: a 49 MB video must not sit in RAM on a small server
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE:
                    out.close()
                    path.unlink(missing_ok=True)
                    raise HTTPException(413, "File too large (Telegram limit ~50 MB) — use a link")
                out.write(chunk)
        m.kind, m.filename, m.path, m.size = ("video" if ext in VIDEO else "document"), name[:200], str(path), size
    elif url.strip():
        if not url.startswith("https://") or len(url) > 500:
            raise HTTPException(400, "Link must start with https://")
        m.kind, m.url = "link", url.strip()
    else:
        raise HTTPException(400, "Attach a file or a link")
    db.add(m)
    db.flush()
    audit(db, scope, "material_create", f"material:{m.id}", kind=m.kind, size=m.size)
    db.commit()
    return _row(m, [])


@router.get("/{mid}/file")
def material_file(mid: int, scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    m = db.get(OnboardingMaterial, mid)
    if not m or not m.path or not Path(m.path).is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(m.path, filename=m.filename)


class SendIn(BaseModel):
    employee_ids: list[int] = Field(min_length=1, max_length=500)
    talk_employee_ids: list[int] = []
    talk_at: datetime | None = None
    talk_with: str | None = Field(default=None, max_length=160)
    message: str = Field(default="", max_length=1000)


@router.post("/{mid}/send")
def material_send(mid: int, body: SendIn, scope: Scope = Depends(require("onboarding")), db: Session = Depends(get_db)):
    m = db.get(OnboardingMaterial, mid)
    if not m:
        raise HTTPException(404, "Not found")
    if not set(body.talk_employee_ids) <= set(body.employee_ids):
        raise HTTPException(400, "Talk people must be among recipients")
    if body.talk_employee_ids and not (body.talk_at and body.talk_with):
        raise HTTPException(400, "Set talk date/time and who holds the talk")
    sent, no_tg = 0, []
    for eid in body.employee_ids:
        e = db.get(Employee, eid)
        if not e or not scope.allows_branch(e.branch_id) or e.status == "fired":
            raise HTTPException(404, f"Employee {eid} not found")
        talk = eid in body.talk_employee_ids
        s = db.scalar(select(MaterialSend).where(MaterialSend.material_id == m.id, MaterialSend.employee_id == eid))
        if not s:
            s = MaterialSend(material_id=m.id, employee_id=eid)
            db.add(s)
        s.sent_at = datetime.now()
        if talk:
            s.talk_at, s.talk_with, s.talk_done = body.talk_at, body.talk_with, False
        if not e.telegram_id:
            no_tg.append(e.full_name)
            continue
        text = f"📚 {m.title}\n" + (f"{body.message}\n" if body.message else "") + (f"{m.description}\n" if m.description else "")
        if m.url:
            text += f"\n🔗 {m.url}"
        if talk:
            text += (f"\n\n🗓 Suhbat · Беседа: {body.talk_at:%d.%m.%Y %H:%M}\n"
                     f"👤 {body.talk_with}")
        db.add(Outbox(telegram_id=e.telegram_id, text=text.strip(), file_path=m.path))
        sent += 1
    audit(db, scope, "material_send", f"material:{m.id}", recipients=len(body.employee_ids), talks=len(body.talk_employee_ids))
    db.commit()
    return {"queued": sent, "without_telegram": no_tg}


@router.get("/{mid}/sends")
def material_sends(mid: int, scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    return [{"id": s.id, "employee_id": s.employee_id, "full_name": s.employee.full_name,
             "branch": s.employee.branch.name if s.employee.branch else None, "telegram": s.employee.telegram_id is not None,
             "sent_at": s.sent_at, "talk_at": s.talk_at, "talk_with": s.talk_with, "talk_done": s.talk_done, "talk_note": s.talk_note}
            for s in db.scalars(select(MaterialSend).where(MaterialSend.material_id == mid).order_by(MaterialSend.talk_at.desc()))
            if scope.allows_branch(s.employee.branch_id)]


class TalkIn(BaseModel):
    note: str = Field(default="", max_length=500)


@router.post("/sends/{sid}/talk-done")
def talk_done(sid: int, body: TalkIn, scope: Scope = Depends(require("onboarding")), db: Session = Depends(get_db)):
    s = db.get(MaterialSend, sid)
    if not s or not s.talk_at or not scope.allows_branch(s.employee.branch_id):
        raise HTTPException(404, "Not found")
    s.talk_done, s.talk_note = True, body.note or None
    audit(db, scope, "material_talk_done", f"send:{s.id}")
    db.commit()
    return {"ok": True}


# ---------------- course: who the material is for, agent-picked plan per employee, progress ----------------

class TagsIn(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    position_ids: list[int] = []
    department_ids: list[int] = []
    day_offset: int = Field(default=0, ge=0, le=60)
    for_new: bool = True


@router.patch("/{mid}")
def material_tags(mid: int, body: TagsIn, scope: Scope = Depends(require("onboarding")), db: Session = Depends(get_db)):
    m = db.get(OnboardingMaterial, mid)
    if not m:
        raise HTTPException(404, "Not found")
    if body.title:
        m.title = body.title
    if body.description is not None:
        m.description = body.description
    m.position_ids, m.department_ids = body.position_ids or None, body.department_ids or None
    m.day_offset, m.for_new = body.day_offset, body.for_new
    audit(db, scope, "material_tags", f"material:{m.id}", positions=body.position_ids, departments=body.department_ids)
    db.commit()
    return _row(m)


def _emp(db: Session, scope: Scope, emp_id: int) -> Employee:
    e = db.get(Employee, emp_id)
    if not e or not scope.allows_branch(e.branch_id):
        raise HTTPException(404, "Employee not found")
    return e


@router.get("/course/{emp_id}")
def course_plan(emp_id: int, ai: bool = True, scope: Scope = Depends(require("onboarding")), db: Session = Depends(get_db)):
    """Agent proposal: what this person should watch / read and on which day. Nothing is sent yet."""
    from ..services import onboarding_media
    e = _emp(db, scope, emp_id)
    return {"employee": {"id": e.id, "full_name": e.full_name, **onboarding_media.profile(e), "telegram": e.telegram_id is not None},
            "items": onboarding_media.plan(db, e, use_ai=ai)}


class CourseIn(BaseModel):
    items: list[dict] = Field(max_length=100)
    start_date: str | None = None


@router.post("/course/{emp_id}")
def course_assign(emp_id: int, body: CourseIn, scope: Scope = Depends(require("onboarding")), db: Session = Depends(get_db)):
    from datetime import date as _date
    from ..services import onboarding_media
    e = _emp(db, scope, emp_id)
    start = _date.fromisoformat(body.start_date) if body.start_date else None
    n = onboarding_media.assign(db, scope, e, body.items, start)
    sent = onboarding_media.deliver_due(db)  # day-0 items go out right away
    db.commit()
    return {"scheduled": n, "sent_now": sent}


@router.get("/employee/{emp_id}")
def course_progress(emp_id: int, scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    e = _emp(db, scope, emp_id)
    rows = []
    for s in db.scalars(select(MaterialSend).where(MaterialSend.employee_id == e.id).order_by(MaterialSend.scheduled_for)):
        m = db.get(OnboardingMaterial, s.material_id)
        rows.append({"id": s.id, "title": m.title, "kind": m.kind, "scheduled_for": s.scheduled_for, "sent_at": s.sent_at if s.queued else None,
                     "viewed_at": s.viewed_at, "reason": s.reason, "talk_at": s.talk_at})
    return {"employee": e.full_name, "telegram": e.telegram_id is not None, "items": rows}
