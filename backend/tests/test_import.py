"""Smartup import: agents become employees once, sales upsert, re-run is idempotent."""
import sqlite3

from sqlalchemy import func, select

from app.importers import smartup
from app.models import Employee, ExternalRef, SalesRecord


def test_smartup_import_idempotent(db, tmp_path):
    p = tmp_path / "smartup.db"
    con = sqlite3.connect(p)
    con.execute("create table monthly_agent_sales (filial_id TEXT, month TEXT, agent TEXT, amount REAL, okb INTEGER, captured_at REAL)")
    con.executemany("insert into monthly_agent_sales values (?,?,?,?,0,0)", [
        ("14338112", "2026-09", "Andijon bozor", 120_000_000), ("14338112", "2026-10", "Andijon bozor", 90_000_000),
        ("19522161", "2026-10", "Samarqand 1", 50_000_000), ("19522161", "2026-10", "Zero agent", 0)])
    con.commit()
    con.close()
    r1 = smartup.run(str(p))
    assert r1["new_people"] == 2 and r1["sales_changed"] == 3  # zero-amount row skipped
    r2 = smartup.run(str(p))
    assert r2["new_people"] == 0 and r2["sales_changed"] == 0
    ids = [x.local_id for x in db.scalars(select(ExternalRef).where(ExternalRef.kind == "employee"))]
    assert db.scalar(select(func.count()).select_from(Employee).where(Employee.id.in_(ids))) == 2
    assert db.scalar(select(SalesRecord.amount).where(SalesRecord.employee_id.in_(ids), SalesRecord.month == "2026-09")) == 120_000_000
