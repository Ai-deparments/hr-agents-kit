from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User
from .rbac import Scope, scope_for_telegram, scope_for_user

ph = PasswordHasher()
_fails: dict[str, list[float]] = {}


def hash_password(p: str) -> str:
    return ph.hash(p)


def check_password(user: User, p: str) -> bool:
    key = user.username
    recent = [t for t in _fails.get(key, []) if t > time.time() - 600]
    if len(recent) >= 8:
        raise HTTPException(429, "Too many attempts, try again in 10 minutes")
    try:
        ph.verify(user.password_hash, p)
        _fails.pop(key, None)
        return True
    except VerifyMismatchError:
        _fails[key] = recent + [time.time()]
        return False


def make_token(sub: str, kind: str, days: int) -> str:
    return jwt.encode({"sub": sub, "kind": kind, "exp": int(time.time()) + days * 86400}, settings().jwt_secret, "HS256")


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired session")


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Login required")
    return authorization[7:]


def current_user(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> User:
    claims = _decode(_bearer(authorization))
    if claims.get("kind") != "panel":
        raise HTTPException(401, "Panel session required")
    user = db.get(User, int(claims["sub"]))
    if not user or not user.active:
        raise HTTPException(401, "User disabled")
    return user


def panel_scope(user: User = Depends(current_user)) -> Scope:
    return scope_for_user(user)


def require(perm: str):
    def dep(scope: Scope = Depends(panel_scope)) -> Scope:
        if not scope.can(perm):
            raise HTTPException(403, f"Permission '{perm}' required")
        return scope
    return dep


# ---------- Telegram Mini App ----------

def verify_init_data(init_data: str, bot_token: str, max_age: int = 3600) -> dict:
    """https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app"""
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", None)
    if not received:
        raise HTTPException(401, "No Telegram signature")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(hmac.new(secret, check.encode(), hashlib.sha256).hexdigest(), received):
        raise HTTPException(401, "Bad Telegram signature")
    if time.time() - int(pairs.get("auth_date", 0)) > max_age:
        raise HTTPException(401, "Telegram signature expired")
    return json.loads(pairs.get("user", "{}"))


def miniapp_telegram_id(authorization: str | None = Header(None)) -> int:
    claims = _decode(_bearer(authorization))
    if claims.get("kind") != "miniapp":
        raise HTTPException(401, "Mini App session required")
    return int(claims["sub"])


def miniapp_scope(tg_id: int = Depends(miniapp_telegram_id), db: Session = Depends(get_db)) -> Scope:
    return scope_for_telegram(db, tg_id)
