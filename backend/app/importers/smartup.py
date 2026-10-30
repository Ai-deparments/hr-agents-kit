"""Import monthly sales per sales agent from a Smartup snapshot (SQLite, table monthly_agent_sales) into SalesRecord.
Each Smartup agent becomes an employee in the "sales agents" department, each filial a branch (names from
company.yaml imports.smartup.filials). Idempotent: re-running updates amounts, never duplicates people.

python -m app.importers.smartup path/to/smartup.db"""
from __future__ import annotations

import sqlite3
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import cfg
from ..db import SessionLocal, init_db
from ..models import Branch, Department, Employee, ExternalRef, Position, Region, SalesRecord
from ..rbac import audit

SRC = "smartup"


def _ref(db: Session, kind: str, ext: str) -> int | None:
    r = db.scalar(select(ExternalRef).where(ExternalRef.source == SRC, ExternalRef.kind == kind, ExternalRef.external_id == ext))
    return r.local_id if r else None


def _link(db: Session, kind: str, ext: str, local_id: int) -> None:
    db.add(ExternalRef(source=SRC, kind=kind, external_id=ext, local_id=local_id))


def _get_or_create(db: Session, model, code: str, **fields):
    obj = db.scalar(select(model).where(model.code == code))
    if not obj:
        obj = model(code=code, **fields)
        db.add(obj)
        db.flush()
    return obj


def _branch(db: Session, filial_id: str, filials: dict) -> int:
    if (bid := _ref(db, "branch", filial_id)) is not None:
        return bid
    info = filials.get(filial_id) or {}
    region_name = info.get("region") or f"Filial {filial_id}"
    code = (info.get("code") or f"SU{filial_id[-4:]}")[:20]
    region = db.scalar(select(Region).where(Region.name == region_name)) or _get_or_create(db, Region, f"R-{code}"[:20], name=region_name)
    b = _get_or_create(db, Branch, f"S-{code}"[:20], name=f"{region_name} · savdo", region_id=region.id, city=region_name, mode="day")
    _link(db, "branch", filial_id, b.id)
    return b.id


def run(path: str) -> dict:
    init_db()
    filials = {str(k): v for k, v in (cfg("imports.smartup.filials") or {}).items()}
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    rows = src.execute("select filial_id, month, agent, amount from monthly_agent_sales where amount > 0").fetchall()
    src.close()
    created = updated = 0
    with SessionLocal() as db:
        dept = db.scalar(select(Department).where(Department.name == cfg("imports.smartup.department", "Savdo agentlari")))
        if not dept:
            dept = Department(name=cfg("imports.smartup.department", "Savdo agentlari"), description="Smartup")
            db.add(dept)
            db.flush()
        pos = _get_or_create(db, Position, "sales_agent", title=cfg("imports.smartup.position", "Savdo agenti"))
        for filial_id, month, agent, amount in rows:
            agent = (agent or "").strip()[:160]
            if not agent or len(month or "") != 7:
                continue
            ext = f"{filial_id}:{agent}"
            eid = _ref(db, "employee", ext)
            if eid is None:
                e = Employee(full_name=agent, branch_id=_branch(db, str(filial_id), filials), department_id=dept.id,
                             position_id=pos.id, status="active", schedule_code="day_9_18")
                db.add(e)
                db.flush()
                _link(db, "employee", ext, e.id)
                eid = e.id
                created += 1
            rec = db.scalar(select(SalesRecord).where(SalesRecord.employee_id == eid, SalesRecord.month == month))
            if rec:
                if rec.amount != round(amount):
                    rec.amount, rec.source = round(amount), SRC
                    updated += 1
            else:
                db.add(SalesRecord(employee_id=eid, month=month, amount=round(amount), source=SRC))
                updated += 1
        audit(db, None, "import_smartup", path, rows=len(rows), new_people=created, sales_changed=updated)
        db.commit()
    return {"rows": len(rows), "new_people": created, "sales_changed": updated}


if __name__ == "__main__":
    print(run(sys.argv[1]))
