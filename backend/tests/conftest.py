import os
import tempfile
from datetime import date
from pathlib import Path

_tmp = Path(tempfile.mkdtemp())
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["LLM_MODE"] = "offline"
os.environ["DEBUG"] = "1"
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-hs256"
os.environ["DEV_TELEGRAM_ID"] = "2001"
os.environ["OWNER_IDS"] = "9999"
os.environ["COMPANY_FILE"] = str(_tmp / "missing.yaml")  # -> falls back to company.example.yaml

import pytest  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app import seed  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed.load_dictionaries(db)
        seed.ensure_admin(db)
        seed.demo(db)
        db.commit()
    yield


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def today():
    return date.today()
