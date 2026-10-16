"""Engagement & anti-fraud APIs: SOP read coverage, anonymous pulse, risk signals, branch geofence."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import miniapp_scope, require
from ..db import get_db
from ..models import Branch, Employee
from ..rbac import Scope, audit
from ..services import engagement

router = APIRouter(prefix="/api/engagement")
mini = APIRouter(prefix="/api/miniapp")


@router.get("/sops")
def sop_coverage(scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    return engagement.sop_coverage(db, scope)


@router.get("/pulse")
def pulse(months: int = 3, scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    return engagement.pulse_summary(db, scope, max(1, min(months, 12)))


@router.get("/risk")
def risk(scope: Scope = Depends(require("hr.write")), db: Session = Depends(get_db)):
    """HR only (not read-only managers): signals are a reason for a conversation, never a decision."""
    return {"note": "Explainable rules, not a prediction about a person. A human decides what to do.",
            "rows": engagement.risk_signals(db, scope)}


class GeoIn(BaseModel):
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    radius_m: int | None = Field(default=None, ge=30, le=2000)


@router.patch("/branches/{bid}/geo")
def branch_geo(bid: int, body: GeoIn, scope: Scope = Depends(require("hr.write")), db: Session = Depends(get_db)):
    if not scope.all_branches:
        raise HTTPException(403, "Only users without branch restriction set geofences")
    b = db.get(Branch, bid)
    if not b:
        raise HTTPException(404, "Not found")
    b.lat, b.lon, b.radius_m = body.lat, body.lon, body.radius_m
    audit(db, scope, "branch_geo", f"branch:{bid}", lat=body.lat, lon=body.lon, radius_m=body.radius_m)
    db.commit()
    return {"id": b.id, "lat": b.lat, "lon": b.lon, "radius_m": b.radius_m}


# ---------------- employee side (Mini App) ----------------

def _me(scope: Scope, db: Session) -> Employee:
    if not scope.employee_id:
        raise HTTPException(403, "Not linked")
    return db.get(Employee, scope.employee_id)


@mini.get("/sops/unread")
def unread(scope: Scope = Depends(miniapp_scope), db: Session = Depends(get_db)):
    return engagement.my_unread(db, _me(scope, db))


@mini.post("/sops/{sop_id}/ack")
def ack(sop_id: int, scope: Scope = Depends(miniapp_scope), db: Session = Depends(get_db)):
    try:
        r = engagement.acknowledge(db, scope, _me(scope, db), sop_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return r


class PulseIn(BaseModel):
    kind: str = "enps"
    score: int = Field(ge=0, le=10)
    reason: str | None = None
    comment: str | None = Field(default=None, max_length=500)


@mini.post("/pulse")
def pulse_answer(body: PulseIn, scope: Scope = Depends(miniapp_scope), db: Session = Depends(get_db)):
    if body.kind not in ("enps", "exit"):
        raise HTTPException(400, "Bad kind")
    ok = engagement.record_pulse(db, _me(scope, db), body.kind, body.score, body.reason, body.comment)
    db.commit()
    return {"ok": ok, "anonymous": True}
