"""AI camera: signed webhook (machine -> us) and the read-only 'Camera' page of the panel."""
from __future__ import annotations

import json
import logging
import time
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import require
from ..config import cfg, settings
from ..db import get_db
from ..rbac import Scope, audit
from ..services import camera

log = logging.getLogger("camera")
router = APIRouter(prefix="/api")


async def _read_capped(request: Request, limit: int) -> bytes:
    if int(request.headers.get("content-length") or 0) > limit:
        raise HTTPException(413, "Body too large")
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > limit:
            raise HTTPException(413, "Body too large")
    return bytes(buf)


@router.post("/webhooks/camera")
async def camera_webhook(request: Request, x_signature: str | None = Header(None), x_timestamp: str | None = Header(None),
                         x_delivery_id: str | None = Header(None), db: Session = Depends(get_db)):
    secret = settings().camera_webhook_secret
    if not secret:
        raise HTTPException(503, "Camera webhook is not configured")
    raw = await _read_capped(request, int(cfg("camera.max_body_kb", 512)) * 1024)
    problem = camera.verify_signature(secret, x_timestamp, x_signature, raw, time.time())
    if problem:
        log.warning("camera webhook rejected: %s", problem)  # never log the body or the headers' values
        raise HTTPException(401, "Bad signature")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Body is not JSON")
    delivery = x_delivery_id or (payload.get("delivery_id") if isinstance(payload, dict) else None)
    try:
        res = camera.handle(db, str(delivery or ""), payload)
        if not res.get("duplicate"):
            audit(db, None, "camera_webhook", str(delivery)[:80], event=payload.get("event"))
        db.commit()
    except camera.BadEvent as e:
        db.rollback()
        raise HTTPException(422, str(e))
    except IntegrityError:  # the same delivery arrived twice at the same moment
        db.rollback()
        return {"ok": True, "duplicate": True}
    return res


@router.get("/camera")
def camera_day(day: date | None = None, scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    return camera.day_summary(db, scope, day or date.today())


@router.get("/camera/days")
def camera_days(days: int = 14, scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    return camera.days_overview(db, scope, max(1, min(days, 62)))
