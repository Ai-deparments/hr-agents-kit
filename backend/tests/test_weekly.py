"""Weekly CEO digest: rich Markdown with tables + Excel with the 3 house-style sheets."""
import io
from datetime import date, timedelta

from openpyxl import load_workbook

from app.rbac import Scope
from app.services import weekly


def test_week_digest(db):
    monday = date.today() - timedelta(days=date.today().weekday() + 7)
    w = weekly.week_data(db, Scope("system", "owner", None, True), monday)
    assert len(w["days"]) == 7 and w["headcount"] >= 1
    md = weekly.week_md(w)
    assert "Haftalik hisobot" in md and "- " in md and "|:-" not in md
    wb = load_workbook(io.BytesIO(weekly.week_excel(w)))
    assert wb.sheetnames == ["DASHBOARD", "DETAILED DATA", "ANALYTICS"]


def test_topic_reports_phone_format(db):
    from app.services import topic_reports as tr
    s = Scope("system", "owner", None, True)
    outs = [tr.analytics_md(db, s), tr.analytics_evening_md(db, s)]
    for fn in (tr.recruiting_md, tr.onboarding_md, tr.payroll_md):
        outs += [fn(db, s), fn(db, s, evening=True)]
    for md in outs:
        assert md is None or (md.startswith("## ") and "|:-" not in md and len(md) < 4000)


def test_checked_in_without_checkout_counts_as_came():
    from app.services import attendance as att
    assert att.came("needs_review", "2026-10-20T09:40") and not att.came("needs_review", None)
    assert att.was_late("needs_review", 25) and not att.was_late("needs_review", 0)
    assert "leave" in att.NOT_SCHEDULED
