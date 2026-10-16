"""Check-in anti-fraud: prove the employee is at the branch.
geo  — Telegram LocationManager / browser GPS inside the branch radius (accuracy must be good enough);
qr   — a 6-digit code that rotates every 60 s, shown on the head's phone (QR) and scanned in the Mini App.
GPS alone can be faked, so 'qr' or 'geo_or_qr' is recommended for pilots with fraud history."""
from __future__ import annotations

import hashlib
import hmac
import math
import secrets
import time
from dataclasses import dataclass

from ..config import cfg
from ..models import Branch

WINDOW_S = 60


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def ensure_secret(branch: Branch) -> str:
    if not branch.qr_secret:
        branch.qr_secret = secrets.token_hex(16)
    return branch.qr_secret


def code_for(branch: Branch, at: float | None = None) -> str:
    window = int((at or time.time()) // WINDOW_S)
    mac = hmac.new(ensure_secret(branch).encode(), f"{branch.id}:{window}".encode(), hashlib.sha256).hexdigest()
    return f"{int(mac[:12], 16) % 1_000_000:06d}"


def qr_payload(branch: Branch) -> dict:
    now = time.time()
    return {"payload": f"HRCHK:{branch.id}:{code_for(branch, now)}", "code": code_for(branch, now),
            "expires_in": WINDOW_S - int(now % WINDOW_S)}


def check_code(branch: Branch, code: str) -> bool:
    code = (code or "").strip().split(":")[-1]
    now = time.time()
    # accept the current and the previous window (clock skew, slow scan)
    return any(hmac.compare_digest(code, code_for(branch, now - k * WINDOW_S)) for k in (0, 1))


@dataclass
class Verdict:
    ok: bool
    verified: str            # geo | qr | none
    distance_m: int | None = None
    reason: str | None = None
    need: str | None = None  # what the client should ask for next: location | qr


def verify(branch: Branch | None, lat: float | None, lon: float | None, accuracy: float | None, code: str | None) -> Verdict:
    mode = cfg("attendance.check_mode", "none")
    if mode == "none" or branch is None:
        return Verdict(True, "none")
    if code and mode in ("qr", "geo_or_qr"):
        if check_code(branch, code):
            return Verdict(True, "qr")
        return Verdict(False, "none", reason="QR code is wrong or expired — scan again", need="qr")
    configured_geo = branch.lat is not None and branch.lon is not None
    if mode in ("geo", "geo_or_qr") and configured_geo:
        if lat is None or lon is None:
            return Verdict(False, "none", reason="Location is needed to check in", need="location")
        dist = int(haversine_m(lat, lon, branch.lat, branch.lon))
        max_acc = int(cfg("attendance.max_gps_accuracy_m", 150))
        radius = branch.radius_m or int(cfg("attendance.default_radius_m", 150))
        if accuracy is not None and accuracy > max_acc:
            return Verdict(False, "none", dist, f"GPS is not precise enough (±{int(accuracy)} m)",
                           need="qr" if mode == "geo_or_qr" else "location")
        if dist <= radius:
            return Verdict(True, "geo", dist)
        return Verdict(False, "none", dist, f"You are {dist} m from the branch (allowed {radius} m)",
                       need="qr" if mode == "geo_or_qr" else None)
    if mode == "qr":
        return Verdict(False, "none", reason="Scan the QR code on the head's phone", need="qr")
    if mode == "geo_or_qr":
        return Verdict(False, "none", reason="Scan the QR code on the head's phone", need="qr")
    # geo mode but the branch has no coordinates yet: allow, but mark as unverified for HR
    return Verdict(True, "none", reason="branch location not configured")
