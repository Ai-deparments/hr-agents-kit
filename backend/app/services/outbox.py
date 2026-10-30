"""Outbox: a decision and its message are written in one transaction; the bot sends each row at most once.
new -> claimed (one conditional UPDATE, committed before sending) -> sent | error. A claimed row is never sent again,
even if the bot crashes mid-send; a double click with the same dedupe key queues nothing twice."""
from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import Outbox


def key(kind: str, ref: object, text: str) -> str:
    return f"{kind}:{ref}:{hashlib.sha256(text.encode()).hexdigest()[:16]}"[:80]


def queue(db: Session, telegram_id: int, text: str, dedupe: str | None = None, topic: str | None = None,
          file_path: str | None = None) -> Outbox | None:
    """None when a message with the same dedupe key is already queued (or sent)."""
    if dedupe and db.scalar(select(Outbox.id).where(Outbox.dedupe_key == dedupe)):
        return None
    o = Outbox(telegram_id=telegram_id, text=text, dedupe_key=dedupe, topic=topic, file_path=file_path)
    db.add(o)
    return o


def claim(db: Session, limit: int = 25) -> list[Outbox]:
    """Rows this worker may send. Each id is claimed by exactly one conditional UPDATE, committed before sending."""
    out = []
    ids = list(db.scalars(select(Outbox.id).where(Outbox.sent_at.is_(None), Outbox.error.is_(None), Outbox.claimed_at.is_(None))
                          .order_by(Outbox.id).limit(limit)))
    for oid in ids:
        if db.execute(update(Outbox).where(Outbox.id == oid, Outbox.claimed_at.is_(None), Outbox.sent_at.is_(None))
                      .values(claimed_at=datetime.now())).rowcount:
            out.append(oid)
    db.commit()
    return [db.get(Outbox, i) for i in out]


def finish(db: Session, o: Outbox, ok: bool, error: str | None = None) -> None:
    if ok:
        o.sent_at = datetime.now()
    else:
        o.error = (error or "send failed")[:300]
    db.commit()
