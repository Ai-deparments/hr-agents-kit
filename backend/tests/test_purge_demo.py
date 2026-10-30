"""purge_demo keeps imported/real people and admin, removes the rest. Runs on its own temp DB."""
import os
import subprocess
import sys
from pathlib import Path


def test_purge_demo_keeps_real(tmp_path):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'p.db'}", "DEBUG": "1"}
    backend = Path(__file__).resolve().parents[1]
    code = r"""
from sqlalchemy import select, func
from app.db import SessionLocal, init_db
from app import seed, purge_demo
from app.models import Employee, ExternalRef, Registration, User, SalesRecord
init_db()
with SessionLocal() as db:
    seed.load_dictionaries(db); seed.ensure_admin(db); seed.demo(db)
    real = Employee(full_name="Real Agent", branch_id=None); db.add(real); db.flush()
    db.add(ExternalRef(source="smartup", kind="employee", external_id="x:Real", local_id=real.id))
    db.add(SalesRecord(employee_id=real.id, month="2026-10", amount=5, source="smartup"))
    db.add(Registration(telegram_id=777777, full_name="Me Test", position_text="x", region_text="y", status="pending"))
    db.commit()
print(purge_demo.purge())
with SessionLocal() as db:
    assert [e.full_name for e in db.scalars(select(Employee))] == ["Real Agent"]
    assert [u.username for u in db.scalars(select(User))] == ["admin"]
    assert [r.telegram_id for r in db.scalars(select(Registration))] == [777777]
    assert db.scalar(select(func.count()).select_from(SalesRecord)) == 1
print("OK")
"""
    r = subprocess.run([sys.executable, "-c", code], cwd=backend, env=env, capture_output=True, text=True)
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr[-2000:]
