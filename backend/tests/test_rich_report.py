"""Rich Markdown reports: tables, heading levels, escaped user text."""
from datetime import date

from app.rbac import Scope
from app.services import reports, tg

OWNER = Scope("system", "owner", None, True)


def test_md_escape_and_table():
    assert tg.md("A|B *x*") == "A\\|B \\*x\\*"
    t = tg.md_table(["a", "b"], [[1, 2]], "lr")
    assert t.splitlines()[1] == "|:---|---:|"


def test_morning_and_evening_rich(db):
    m = reports.morning_md(db, OWNER, date.today())
    assert "## " in m and "- " in m and "#### " in m and "|:-" not in m  # phone: lists, no wide tables
    assert m.count("\n# ") + m.startswith("# ") <= 1  # at most one top-level (urgent) heading
    e = reports.evening_md(db, OWNER, date.today())
    assert e.startswith("## ") and "Kun yakuni" in e and len(e) < 32000
