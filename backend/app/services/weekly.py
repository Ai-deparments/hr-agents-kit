"""Weekly CEO digest (deterministic, no LLM): attendance by day, discipline leaders, people flow, hiring, onboarding,
documents. Rich Markdown for Telegram + a BI-style Excel (DASHBOARD / DETAILED DATA / ANALYTICS)."""
from __future__ import annotations

import io
from collections import defaultdict
from datetime import date, datetime, timedelta

from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import cfg
from ..models import Candidate, CandidateStep, Employee, HrDoc, InterviewSlot, MaterialSend, Vacancy
from ..rbac import Scope
from . import attendance as att
from . import tg

DAYS = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]


def week_data(db: Session, scope: Scope, monday: date) -> dict:
    days, per_emp = [], defaultdict(lambda: {"late": 0, "late_min": 0, "unmarked": 0, "came": 0, "sched": 0, "hours": 0.0})
    for i in range(7):
        d = monday + timedelta(days=i)
        if d > date.today():
            break
        s = att.day_summary(db, scope, d)
        days.append({"date": d, "sched": s["scheduled"], "came": s["came"], "late": s["late"], "unmarked": s["unmarked"]})
        for r in s["rows"]:
            if r["status"] in att.NOT_SCHEDULED:
                continue
            p = per_emp[(r["employee_id"], r["full_name"])]
            p["sched"] += 1
            p["came"] += int(att.came(r["status"], r["check_in"]))
            p["late"] += int(att.was_late(r["status"], r["late_min"]))
            p["late_min"] += r["late_min"] or 0
            p["unmarked"] += int(r["status"] == "unmarked")
            p["hours"] += r["worked_hours"] or 0
    a, b = datetime.combine(monday, datetime.min.time()), datetime.combine(monday + timedelta(days=7), datetime.min.time())
    end = monday + timedelta(days=6)

    def cnt(q):
        return db.scalar(q) or 0
    return {
        "monday": monday, "end": end, "days": days,
        "people": sorted(({"id": k[0], "name": k[1], **v} for k, v in per_emp.items()), key=lambda x: (-x["late"], -x["late_min"])),
        "headcount": cnt(select(func.count(Employee.id)).where(Employee.status != "fired")),
        "hired": cnt(select(func.count(Employee.id)).where(Employee.hire_date.between(monday, end))),
        "fired": cnt(select(func.count(Employee.id)).where(Employee.fire_date.between(monday, end))),
        "vacancies_open": cnt(select(func.count(Vacancy.id)).where(Vacancy.status == "open")),
        "candidates_new": cnt(select(func.count(Candidate.id)).where(Candidate.created_at >= a, Candidate.created_at < b)),
        "interviews": cnt(select(func.count(InterviewSlot.id)).where(InterviewSlot.status.in_(("booked", "done")),
                                                                     InterviewSlot.starts_at >= a, InterviewSlot.starts_at < b)),
        "offers_accepted": cnt(select(func.count(CandidateStep.id)).where(CandidateStep.kind == "offer", CandidateStep.status == "done",
                                                                          CandidateStep.answered_at >= a, CandidateStep.answered_at < b)),
        "materials_sent": cnt(select(func.count(MaterialSend.id)).where(MaterialSend.sent_at >= a, MaterialSend.sent_at < b)),
        "materials_viewed": cnt(select(func.count(MaterialSend.id)).where(MaterialSend.viewed_at >= a, MaterialSend.viewed_at < b)),
        "docs": cnt(select(func.count(HrDoc.id)).where(HrDoc.created_at >= a, HrDoc.created_at < b)),
    }


def _pct(a: int, b: int) -> str:
    return f"{round(100 * a / b)}%" if b else "—"


def week_md(w: dict) -> str:
    M, E = tg.md, tg.me
    sched, came = sum(x["sched"] for x in w["days"]), sum(x["came"] for x in w["days"])
    late, unm = sum(x["late"] for x in w["days"]), sum(x["unmarked"] for x in w["days"])
    out = [f"## {E('chart_up')} Haftalik hisobot — {w['monday']:%d.%m}–{w['end']:%d.%m}",
           f"- Davomat: **{_pct(came, sched)}**\n- Kechikish: **{late}**\n- Belgilanmagan kun: **{unm}**\n"
           f"- Ishga kirdi / ketdi: **{w['hired']}** / **{w['fired']}**",
           f"### {E('calendar')} Kunlar", "\n".join(
               f"- {DAYS[x['date'].weekday()]} {x['date']:%d.%m} — {x['came']}/{x['sched']}" + (f", kechikdi {x['late']}" if x["late"] else "")
               for x in w["days"] if x["sched"])]
    worst = [p for p in w["people"] if p["late"]][:5]
    if worst:
        out += [f"### {E('warning')} Ko'p kechikkanlar", "\n".join(f"- {M(p['name'])} — {p['late']} kun, {p['late_min']} daq" for p in worst)]
    hire = [f"Yangi nomzod: **{w['candidates_new']}**", f"Suhbat: **{w['interviews']}**", f"Taklif qabul: **{w['offers_accepted']}**",
            f"Onboarding: **{w['materials_sent']}** yuborildi, **{w['materials_viewed']}** ko'rildi", f"HR hujjat: **{w['docs']}**"]
    out += [f"### {E('user')} Yollash va onboarding", "\n".join(f"- {x}" for x in hire),
            f"#### {E('idea')} *Batafsil — Excel faylda.*"]
    return "\n\n".join(out)


def week_text(w: dict) -> str:
    sched, came = sum(x["sched"] for x in w["days"]), sum(x["came"] for x in w["days"])
    late = sum(x["late"] for x in w["days"])
    return (f"<b>Haftalik HR hisobot — {w['monday']:%d.%m}–{w['end']:%d.%m.%Y}</b>\n"
            f"Xodimlar: <b>{w['headcount']}</b> · davomat: <b>{_pct(came, sched)}</b> · kechikish: <b>{late}</b>\n"
            f"Ishga kirdi: {w['hired']} · ketdi: {w['fired']} · nomzod: {w['candidates_new']} · suhbat: {w['interviews']}\n"
            "Batafsil — Excel faylda.")


def week_excel(w: dict) -> bytes:
    from . import xlsx_style as X
    wb = Workbook()
    wb.calculation.fullCalcOnLoad = True
    dash = wb.active
    dash.title = "DASHBOARD"
    data = wb.create_sheet("DETAILED DATA")
    ana = wb.create_sheet("ANALYTICS")
    period = f"{w['monday']:%d.%m}–{w['end']:%d.%m.%Y}"

    X.sheet(data, {"A": 2, "B": 32, "C": 12, "D": 12, "E": 12, "F": 14, "G": 14, "H": 12})
    X.title(data, "Xodimlar — hafta", f"{period} · {len(w['people'])} xodim · manba: {cfg('attendance.source', 'telegram')}", 8)
    d1, d2 = X.table(data, 4, 2, ["F.I.Sh", "Rejada", "Keldi", "Kechikdi", "Kechikish, daq", "Belgilanmagan", "Ish soati"],
                     [[p["name"], p["sched"], p["came"], p["late"], p["late_min"], p["unmarked"], round(p["hours"], 1)]
                      for p in w["people"]], {6: "0.0"})

    X.sheet(ana, {"A": 2, "B": 16, "C": 12, "D": 12, "E": 12, "F": 14, "G": 12})
    X.title(ana, "Kunlar bo'yicha", f"{period} · % ustuni formulalar bilan", 7)
    days = [x for x in w["days"] if x["sched"]]
    rows = [[f"{DAYS[x['date'].weekday()]} {x['date']:%d.%m}", x["sched"], x["came"], x["late"], x["unmarked"], f"=IFERROR(D{5 + i}/C{5 + i},\"—\")"]
            for i, x in enumerate(days)]
    a1, a2 = X.table(ana, 4, 2, ["Kun", "Rejada", "Keldi", "Kechikdi", "Belgilanmagan", "Davomat, %"], rows, {5: "0%"},
                     filter_=False, freeze=False)
    if days:
        X.good_bad(ana, f"G{a1}:G{a2}", 0.9, 0.75)
        ana.add_chart(X.bar_chart("Rejada va kelganlar", ana, (2, a1, a2), [(3, a1, a2), (4, a1, a2)], [X.LINE, X.BLUE], "xodim"),
                      f"B{a2 + 3}")

    X.sheet(dash, {"A": 2, **{c: 14 for c in "BCDEFGHIJKLM"}})
    X.title(dash, f"Haftalik HR hisobot — {cfg('company.name', '')}", f"Davr: {period}", 13)
    rng = (f"ANALYTICS!$C${a1}:$C${a2}", f"ANALYTICS!$D${a1}:$D${a2}", f"ANALYTICS!$E${a1}:$E${a2}")
    X.kpi(dash, 4, 2, "Xodimlar", f"={w['headcount']}", note="faol, hafta oxirida")
    X.kpi(dash, 4, 4, "Davomat", f"=IFERROR(SUM({rng[1]})/SUM({rng[0]}),0)" if days else "=0", "0%", note="keldi / rejada")
    X.kpi(dash, 4, 6, "Kechikishlar", f"=SUM({rng[2]})" if days else "=0", note="hafta bo'yi", accent=X.RED)
    X.kpi(dash, 4, 8, "Ishga kirdi", f"={w['hired']}", note="hire date shu hafta")
    X.kpi(dash, 4, 10, "Ketdi", f"={w['fired']}", note="TimePay / panel", accent=X.RED)
    X.kpi(dash, 4, 12, "Yangi nomzod", f"={w['candidates_new']}", note=f"suhbat: {w['interviews']}")
    X.good_bad(dash, "D5", 0.9, 0.75)
    X.section(dash, 8, 2, "Kunlar bo'yicha davomat")
    if days:
        dash.add_chart(X.bar_chart("Rejada / keldi", ana, (2, a1, a2), [(3, a1, a2), (4, a1, a2)], [X.LINE, X.BLUE], "xodim"), "B9")
    X.section(dash, 25, 2, "Xulosalar")
    worst = [p for p in w["people"] if p["late"]]
    X.notes(dash, 26, 2, 12, [
        f"Davr: {period}.",
        f"Eng ko'p kechikkan: {worst[0]['name']} — {worst[0]['late']} kun, {worst[0]['late_min']} daqiqa." if worst else "Kechikishlar yo'q.",
        f"Yollash: {w['candidates_new']} nomzod, {w['interviews']} suhbat, {w['offers_accepted']} taklif qabul qilindi.",
        f"Onboarding: {w['materials_sent']} material yuborildi, {w['materials_viewed']} ko'rildi; HR hujjatlar: {w['docs']}.",
        "Belgilanmagan — kelmagan degani emas: rahbar tasdiqlashi kerak."])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
