"""Deterministic reports (no LLM): same format, same time, unknown = '—'."""
from __future__ import annotations

import io
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import cfg
from ..rbac import Scope
from . import attendance as att
from . import people
from . import tg

STATUS_LABEL = {"present": "came", "late": "late", "on_shift": "on shift", "absent": "absent", "leave": "leave",
                "unmarked": "not marked", "off": "day off", "needs_review": "review", "conflict": "conflict"}


def _safe(v):
    """Excel/CSV formula injection guard: text starting with = + - @ is stored as plain text."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _bar(part: int, total: int, width: int = 10) -> str:
    if not total:
        return "—"
    n = round(width * part / total)
    return "█" * n + "░" * (width - n)


def _groups(db: Session, s: dict) -> dict[str, dict]:
    """Per department (or per branch when departments are not used): scheduled / came / late."""
    from ..models import Employee
    dept = {e.id: (e.department.name if e.department else None) for e in db.scalars(select(Employee))}
    use_dept = any(dept.get(r["employee_id"]) for r in s["rows"])
    g: dict[str, dict] = {}
    for r in s["rows"]:
        if r["status"] in att.NOT_SCHEDULED:
            continue
        k = (dept.get(r["employee_id"]) if use_dept else r["branch"]) or "—"
        v = g.setdefault(k, {"sched": 0, "came": 0, "late": 0})
        v["sched"] += 1
        v["came"] += att.came(r["status"], r["check_in"])
        v["late"] += att.was_late(r["status"], r["late_min"])
    return g


def _table(g: dict[str, dict]) -> str:
    """Aligned 'table' inside <pre> (bots have no real tables)."""
    w = min(18, max((len(k) for k in g), default=4))
    rows = [f"{k[:w]:<{w}} {v['came']:>2}/{v['sched']:<2} {_bar(v['came'], v['sched'], 8)}" for k, v in
            sorted(g.items(), key=lambda kv: kv[1]["came"] / (kv[1]["sched"] or 1))]
    return "<pre>" + _esc("\n".join(rows)) + "</pre>"


def _pct(a: int, b: int) -> str:
    return f"{round(100 * a / b)}%" if b else "—"


def morning_md(db: Session, scope: Scope, d: date | None = None, now: datetime | None = None) -> str:
    """Rich message for a phone: heading, key lines, short lists (no wide tables)."""
    d = d or date.today()
    s = att.day_summary(db, scope, d, now=now)
    g = _groups(db, s)
    M, E = tg.md, tg.me
    rate = s["came"] / s["scheduled"] if s["scheduled"] else 1
    out = []
    if s["scheduled"] and rate < 0.6:  # the one urgent thing gets the biggest heading
        out.append(f"# {E('siren')} Davomat past: {_pct(s['came'], s['scheduled'])}")
    out += [f"## {E('signal')} Davomat — {d:%d.%m}, ertalab",
            f"- Ishda: **{s['came']}** / {s['scheduled']} ({_pct(s['came'], s['scheduled'])})\n"
            f"- Kechikdi: **{s['late']}**\n- Belgilamagan: **{s['unmarked']}**"]
    weak = sorted(((k, v) for k, v in g.items() if v["sched"] and v["came"] < v["sched"]),
                  key=lambda kv: kv[1]["came"] / kv[1]["sched"])[:4]
    if len(g) > 1 and weak:
        out += [f"### {E('chart')} Diqqat: bo'limlar", "\n".join(
            f"- {M(k)} — {v['came']}/{v['sched']}" + (f", kechikdi {v['late']}" if v["late"] else "") for k, v in weak)]
    late = sorted((r for r in s["rows"] if att.was_late(r["status"], r["late_min"])), key=lambda r: -(r["late_min"] or 0))[:12]
    if late:
        out += [f"### {E('pin')} Kechikkanlar", "\n".join(
            f"- {M(r['full_name'])} — `{r['check_in'][11:16]}`, +{r['late_min']} daq" for r in late)]
    unmarked = [r for r in s["rows"] if r["status"] == "unmarked"]
    if unmarked:
        names = ", ".join(M(r["full_name"]) for r in unmarked[:15]) + (f" va yana {len(unmarked) - 15}" if len(unmarked) > 15 else "")
        out += [f"### {E('user')} Belgilamaganlar", names]
    if s.get("untracked"):
        out += [f"#### {E('eyes')} TimePay'da 30 kundan beri belgi yo'q (foizga kirmaydi): "
                + ", ".join(M(n) for n in s["untracked"][:10])]
    out += [f"#### {E('idea')} *Belgilamagan — kelmagan degani emas. Batafsil — Excel faylda.*"]
    return "\n\n".join(out)


def evening_md(db: Session, scope: Scope, d: date | None = None, now: datetime | None = None) -> str:
    d = d or date.today()
    s = att.day_summary(db, scope, d, now=now)
    M, E = tg.md, tg.me
    worked = [r["worked_hours"] for r in s["rows"] if r["worked_hours"]]
    avg = f"{sum(worked) / len(worked):.1f}".replace(".", ",") if worked else "—"
    review = [r for r in s["rows"] if r["status"] in ("needs_review", "conflict")]
    out = [f"## {E('moon')} Kun yakuni — {d:%d.%m}",
           f"- Keldi: **{s['came']}** / {s['scheduled']} ({_pct(s['came'], s['scheduled'])})\n- Kechikdi: **{s['late']}**\n"
           f"- O'rtacha ish vaqti: **{avg} soat**" + (f"\n- Tekshirish kerak: **{len(review)}**" if review else "")]
    if review:
        out += [f"### {E('warning')} Chiqishni belgilamaganlar", "\n".join(
            f"- {M(r['full_name'])} — kirish `{(r['check_in'] or '—')[11:16] or '—'}`" for r in review[:12])]
    top = sorted((r for r in s["rows"] if r["worked_hours"]), key=lambda r: -r["worked_hours"])[:3]
    if top:
        out += [f"### {E('trophy')} Eng ko'p ishlaganlar", "\n".join(
            f"- {M(r['full_name'])} — {str(r['worked_hours']).replace('.', ',')} soat" for r in top)]
    out += [f"#### {E('idea')} *Batafsil — Excel faylda.*"]
    return "\n\n".join(out)


def morning_text(db: Session, scope: Scope, d: date | None = None, now: datetime | None = None) -> str:
    d = d or date.today()
    s = att.day_summary(db, scope, d, now=now)
    g = _groups(db, s)
    parts = [f"{tg.e('signal')} <b>Davomat — {d:%d.%m}, ertalabki hisobot</b>",
             f"{tg.e('chart_up')} Ishda: <b>{s['came']}</b> / {s['scheduled']} · kechikdi: <b>{s['late']}</b> · "
             f"belgilamagan: <b>{s['unmarked']}</b>"]
    weak = [(k, v) for k, v in g.items() if v["sched"] and v["came"] / v["sched"] < 0.75]
    if weak:
        k, v = min(weak, key=lambda kv: kv[1]["came"] / kv[1]["sched"])
        parts[-1] += f"\n{tg.e('eyes')} Diqqat: <b>{_esc(k)}</b> — {v['came']}/{v['sched']} keldi"
    best = [(k, v) for k, v in g.items() if v["sched"] >= 2 and v["came"] == v["sched"] and not v["late"]]
    if best:
        k, v = max(best, key=lambda kv: kv[1]["sched"])
        parts[-1] += f"\n{tg.e('top')} Eng intizomli: <b>{_esc(k)}</b> — {v['came']}/{v['sched']}"
    if len(g) > 1:
        parts.append(_table(g))
    late = sorted((r for r in s["rows"] if att.was_late(r["status"], r["late_min"])), key=lambda r: -(r["late_min"] or 0))[:15]
    if late:
        parts.append(f"<blockquote expandable>{tg.e('pin')} <b>Kechikkanlar</b>\n" + "\n".join(
            f"{_esc(r['full_name'])} — {r['check_in'][11:16]} (+{r['late_min']} daq)" for r in late) + "</blockquote>")
    unmarked = [r for r in s["rows"] if r["status"] == "unmarked"][:25]
    if unmarked:
        parts.append(f"<blockquote expandable>{tg.e('user')} <b>Belgilamaganlar</b>\n" +
                     "\n".join(_esc(r["full_name"]) for r in unmarked) + "</blockquote>")
    parts.append(f"{tg.e('idea')} <i>Belgilamagan — kelmagan degani emas. Manba: {_esc(cfg('attendance.source', 'telegram'))}</i>")
    return "\n\n".join(parts)


def evening_text(db: Session, scope: Scope, d: date | None = None, now: datetime | None = None) -> str:
    d = d or date.today()
    s = att.day_summary(db, scope, d, now=now)
    g = _groups(db, s)
    worked = [r["worked_hours"] for r in s["rows"] if r["worked_hours"]]
    avg = f"{sum(worked) / len(worked):.1f}".replace(".", ",") if worked else "—"
    review = [r for r in s["rows"] if r["status"] in ("needs_review", "conflict")]
    parts = [f"{tg.e('moon')} <b>Kun yakuni — {d:%d.%m.%Y}</b>",
             f"{tg.e('check')} Keldi: <b>{s['came']}</b> / {s['scheduled']} · kechikdi: <b>{s['late']}</b>\n"
             f"{tg.e('clock')} O'rtacha ish vaqti: <b>{avg} soat</b>"
             + (f"\n{tg.e('warning')} Tekshirish kerak: <b>{len(review)}</b> (chiqish belgilanmagan)" if review else "")
             + (f"\n{tg.e('moon')} Smenada (tungi/sutkalik): <b>{s['on_shift']}</b>" if s["on_shift"] else "")]
    if len(g) > 1:
        parts.append(_table(g))
    if review:
        parts.append(f"<blockquote expandable>{tg.e('pin')} <b>Chiqishni belgilamaganlar</b>\n" +
                     "\n".join(f"{_esc(r['full_name'])} — kirish {(r['check_in'] or '—')[11:16]}" for r in review[:25]) + "</blockquote>")
    top = sorted((r for r in s["rows"] if r["worked_hours"]), key=lambda r: -r["worked_hours"])[:5]
    if top:
        parts.append(f"<blockquote expandable>{tg.e('trophy')} <b>Eng ko'p ishlaganlar</b>\n" + "\n".join(
            f"{_esc(r['full_name'])} — {str(r['worked_hours']).replace('.', ',')} soat" for r in top) + "</blockquote>")
    parts.append(f"{tg.e('idea')} <i>Batafsil — ilovadagi Excel hisobotda.</i>")
    return "\n\n".join(parts)


STATUS_UZ = {"present": "Keldi", "late": "Kechikdi", "on_shift": "Smenada", "absent": "Kelmadi", "leave": "Ta'til",
             "unmarked": "Belgilanmagan", "off": "Dam olish", "needs_review": "Tekshirish", "conflict": "Ziddiyat",
             "untracked": "TimePay yo'q"}
OUT = ("Dam olish", "Ta'til", "TimePay yo'q")  # not expected at work / not tracked
CAME = ("Keldi", "Kechikdi", "Smenada", "Tekshirish")  # Tekshirish = checked in, no check-out


def _dept_map(db: Session) -> dict[int, str]:
    from ..models import Employee
    return {e.id: (e.department.name if e.department else "—") for e in db.scalars(select(Employee))}


def day_excel(db: Session, scope: Scope, d: date) -> bytes:
    """BI-style attendance day report: DASHBOARD (formulas over DATA) / DETAILED DATA / ANALYTICS per department."""
    from . import xlsx_style as X
    s = att.day_summary(db, scope, d)
    dept = _dept_map(db)
    rows = [r for r in s["rows"] if r["status"] != "not_employed"]
    wb = Workbook()
    wb.calculation.fullCalcOnLoad = True
    dash = wb.active
    dash.title = "DASHBOARD"
    data = wb.create_sheet("DETAILED DATA")
    ana = wb.create_sheet("ANALYTICS")

    # DETAILED DATA
    X.sheet(data, {"A": 2, "B": 30, "C": 22, "D": 24, "E": 20, "F": 15, "G": 11, "H": 11, "I": 11, "J": 12, "K": 12})
    X.title(data, "Davomat — batafsil", f"{d:%d.%m.%Y} · {len(rows)} xodim · manba: {cfg('attendance.source', 'telegram')}", 11)
    hdr = ["F.I.Sh", "Bo'lim", "Lavozim", "Filial", "Holat", "Kirish", "Chiqish", "Ish soati", "Kechikish, daq", "Manba"]
    body = []
    for r in sorted(rows, key=lambda r: (dept.get(r["employee_id"], ""), r["full_name"])):
        body.append([_safe(r["full_name"]), _safe(dept.get(r["employee_id"], "—")), _safe(r["position"] or "—"),
                     _safe(r["branch"]), STATUS_UZ.get(r["status"], r["status"]),
                     (r["check_in"] or "")[11:16] or "—", (r["check_out"] or "")[11:16] or "—",
                     r["worked_hours"] if r["worked_hours"] is not None else None, r["late_min"] or 0, r["source"] or "—"])
    d1, d2 = X.table(data, 4, 2, hdr, body, {7: "0.0", 8: "0"})
    st, dp, hrs, lt = (f"'DETAILED DATA'!$F${d1}:$F${d2}", f"'DETAILED DATA'!$C${d1}:$C${d2}",
                       f"'DETAILED DATA'!$I${d1}:$I${d2}", f"'DETAILED DATA'!$J${d1}:$J${d2}")

    def came(extra: str = "") -> str:
        return "+".join(f'COUNTIFS({st},"{x}"{extra})' for x in CAME)

    # ANALYTICS — per department, all formulas over DATA
    X.sheet(ana, {"A": 2, "B": 28, "C": 12, "D": 12, "E": 12, "F": 14, "G": 14, "H": 14})
    X.title(ana, "Bo'limlar kesimida tahlil", f"{d:%d.%m.%Y} · barcha qiymatlar DETAILED DATA varag'idan formulalar bilan", 8)
    depts = sorted({b[1] for b in body})
    arows = []
    for i, name in enumerate(depts):
        r = 5 + i
        k = f',{dp},$B{r}'
        arows.append([name, f'=COUNTIFS({dp},$B{r},' + ",".join(f'{st},"<>{x}"' for x in OUT) + ")", f"={came(k)}", f'=COUNTIFS({dp},$B{r},{st},"Kechikdi")',
                      f'=COUNTIFS({dp},$B{r},{st},"Belgilanmagan")', f'=IFERROR(D{r}/C{r},"—")',
                      f'=IFERROR(AVERAGEIFS({hrs},{dp},$B{r},{hrs},">0"),"—")'])
    a1, a2 = X.table(ana, 4, 2, ["Bo'lim", "Rejada", "Keldi", "Kechikdi", "Belgilanmagan", "Davomat, %", "O'rt. soat"],
                     arows, {4: "0%", 5: "0.0"}, filter_=False, freeze=False)
    tr = a2 + 1
    ana.cell(tr, 2, "Jami").font = X.f(10.5, True, X.NAVY)
    for j, col in enumerate("CDEF"):
        c = ana.cell(tr, 3 + j, f"=SUM({col}{a1}:{col}{a2})")
        c.font = X.f(10.5, True, X.NAVY)
        c.alignment = X.Alignment(horizontal="right", indent=1)
    c = ana.cell(tr, 7, f'=IFERROR(D{tr}/C{tr},"—")')
    c.number_format, c.font = "0%", X.f(10.5, True, X.NAVY)
    X.good_bad(ana, f"G{a1}:G{tr}", 0.9, 0.75)
    if depts:
        ana.add_chart(X.bar_chart("Rejada va kelganlar", ana, (2, a1, a2), [(3, a1, a2), (4, a1, a2)], [X.LINE, X.BLUE], "xodim"),
                      f"B{tr + 3}")

    # DASHBOARD
    X.sheet(dash, {"A": 2, **{c: 14 for c in "BCDEFGHIJKLM"}})
    X.title(dash, f"Davomat hisoboti — {cfg('company.name', '')}", f"Sana: {d:%d.%m.%Y} · manba: {cfg('attendance.source', 'telegram')}", 13)
    X.kpi(dash, 4, 2, "Rejada", "=COUNTIFS(" + ",".join(f'{st},"<>{x}"' for x in OUT) + ")", note="bugun ishlashi kerak")
    X.kpi(dash, 4, 4, "Keldi", f"={came()}", note="kech kelganlar bilan")
    X.kpi(dash, 4, 6, "Davomat", f'=IFERROR(D5/B5,0)', "0%", note="keldi / rejada")
    X.kpi(dash, 4, 8, "Kechikdi", f'=COUNTIF({st},"Kechikdi")', note="ish boshlanishidan keyin", accent=X.RED)
    X.kpi(dash, 4, 10, "Belgilanmagan", f'=COUNTIF({st},"Belgilanmagan")', note="kelmagan degani emas", accent=X.MUTED)
    X.kpi(dash, 4, 12, "O'rt. ish soati", f'=IFERROR(AVERAGEIF({hrs},">0"),0)', "0.0", note="chiqish belgilanganlar")
    X.good_bad(dash, "F5", 0.9, 0.75)
    X.section(dash, 8, 2, "Bo'limlar bo'yicha")
    if depts:
        dash.add_chart(X.bar_chart("Bo'limlar: rejada / keldi", ana, (2, a1, a2), [(3, a1, a2), (4, a1, a2)],
                                   [X.LINE, X.BLUE], "xodim"), "B9")
    X.section(dash, 25, 2, "Xulosalar")
    sched = sum(1 for b in body if b[4] not in OUT)
    cm = sum(1 for b in body if b[4] in CAME)
    late_rows = sorted((b for b in body if b[4] == "Kechikdi"), key=lambda b: -b[8])
    worst = min(((n, sum(1 for b in body if b[1] == n and b[4] in CAME), sum(1 for b in body if b[1] == n and b[4] not in OUT))
                 for n in depts), key=lambda x: (x[1] / x[2]) if x[2] else 1, default=None)
    concl = [f"Bugun {cm} / {sched} xodim ishda" + (f" ({round(100 * cm / sched)}%)." if sched else "."),
             (f"Eng ko'p kechikkan: {late_rows[0][0]} — {late_rows[0][8]} daqiqa." if late_rows else "Kechikishlar yo'q."),
             (f"Diqqat talab qiladi: {worst[0]} — {worst[1]}/{worst[2]} keldi." if worst and worst[2] and worst[1] < worst[2]
              else "Barcha bo'limlarda to'liq davomat."),
             "Belgilanmagan — kelmagan degani emas: rahbar tasdiqlashi kerak."]
    X.notes(dash, 26, 2, 12, concl)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def tabel_excel(db: Session, scope: Scope, month: str, branch_id: int | None = None) -> bytes:
    """BI-style month tabel: DASHBOARD / DETAILED DATA (day grid) / ANALYTICS per department, formulas over the grid."""
    from openpyxl.utils import get_column_letter as L
    from . import xlsx_style as X
    t = att.month_tabel(db, scope, month, branch_id)
    dept = _dept_map(db)
    wb = Workbook()
    wb.calculation.fullCalcOnLoad = True
    dash = wb.active
    dash.title = "DASHBOARD"
    data = wb.create_sheet("DETAILED DATA")
    ana = wb.create_sheet("ANALYTICS")

    # DETAILED DATA: name, dept, position, days..., worked, norm, days, late, review, unknown
    nd = len(t["days"])
    X.sheet(data, {"A": 2, "B": 28, "C": 20, "D": 20, **{L(5 + i): 5.2 for i in range(nd)},
                   **{L(5 + nd + i): 11 for i in range(6)}})
    X.title(data, f"Tabel — {month}", "Kun katagida: ishlangan soat yoki kod (L — kechikish, A — kelmagan, V — ta'til, "
                                      "R — tekshirish, ? — belgilanmagan)", 5 + nd + 5)
    hdr = ["F.I.Sh", "Bo'lim", "Lavozim"] + [str(x)[-2:] for x in t["days"]] + ["Ish soati", "Norma", "Ish kuni", "Kechikish",
                                                                               "Tekshirish", "Belgilanmagan"]
    body, codes = [], []
    for row in sorted(t["rows"], key=lambda r: (dept.get(r["employee_id"], ""), r["full_name"])):
        body.append([_safe(row["full_name"]), _safe(dept.get(row["employee_id"], "—")), _safe(row["position"] or "—")] +
                    [(c["h"] if c["h"] else c["c"]) for c in row["cells"]] +
                    [row["worked_hours"], row["norm_hours"], row["worked_days"], row["late_days"], row["review_days"],
                     row["unknown_days"]])
        codes.append([c["c"] for c in row["cells"]])
    d1, d2 = X.table(data, 4, 2, hdr, body, {3 + nd: "0.0", 4 + nd: "0.0"})
    tint = {"L": "FEF3C7", "A": "FEE2E2", "V": "DBEAFE", "R": "FCE7F3", "!": "FEE2E2", "?": "F1F5F9"}
    for i, cs in enumerate(codes):
        for j, code in enumerate(cs):
            cell = data.cell(d1 + i, 5 + j)
            cell.alignment = X.Alignment(horizontal="center")
            cell.font = X.f(9)
            if code in tint:
                cell.fill = X.fill(tint[code])
    data.freeze_panes = data.cell(d1, 5)
    W, N, DY, LT, RV, UN = (L(5 + nd + k) for k in range(6))

    def rng(col: str) -> str:
        return f"'DETAILED DATA'!${col}${d1}:${col}${d2}"

    # ANALYTICS per department
    X.sheet(ana, {"A": 2, "B": 28, "C": 11, "D": 13, "E": 13, "F": 13, "G": 13, "H": 13})
    X.title(ana, "Bo'limlar kesimida tabel tahlili", f"{month} · barcha qiymatlar formulalar bilan", 8)
    depts = sorted({b[1] for b in body})
    arows = []
    for i, name in enumerate(depts):
        r = 5 + i
        dp = rng("C")
        arows.append([name, f"=COUNTIF({dp},$B{r})", f"=SUMIF({dp},$B{r},{rng(W)})", f"=SUMIF({dp},$B{r},{rng(N)})",
                      f'=IFERROR(D{r}/E{r},"—")', f"=SUMIF({dp},$B{r},{rng(LT)})", f"=SUMIF({dp},$B{r},{rng(UN)})"])
    a1, a2 = X.table(ana, 4, 2, ["Bo'lim", "Xodim", "Ish soati", "Norma, soat", "Bajarilish, %", "Kechikish, kun",
                                 "Belgilanmagan, kun"], arows, {2: "#,##0.0", 3: "#,##0.0", 4: "0%"}, filter_=False, freeze=False)
    tr = a2 + 1
    ana.cell(tr, 2, "Jami").font = X.f(10.5, True, X.NAVY)
    for col in "CDEGH":
        c = ana.cell(tr, " ABCDEFGH".index(col), f"=SUM({col}{a1}:{col}{a2})")
        c.font, c.number_format = X.f(10.5, True, X.NAVY), "#,##0.0" if col in "DE" else "#,##0"
    c = ana.cell(tr, 6, f'=IFERROR(D{tr}/E{tr},"—")')
    c.font, c.number_format = X.f(10.5, True, X.NAVY), "0%"
    X.good_bad(ana, f"F{a1}:F{tr}", 0.95, 0.8)
    if depts:
        ana.add_chart(X.bar_chart("Ish soati va norma", ana, (2, a1, a2), [(5, a1, a2), (4, a1, a2)], [X.LINE, X.BLUE], "soat"),
                      f"B{tr + 3}")

    # DASHBOARD
    X.sheet(dash, {"A": 2, **{c: 14 for c in "BCDEFGHIJKLM"}})
    X.title(dash, f"Tabel — {cfg('company.name', '')}", f"Davr: {month} · {len(body)} xodim", 13)
    X.kpi(dash, 4, 2, "Xodimlar", f"=COUNTA({rng('B')})", note="tabeldagi xodimlar")
    X.kpi(dash, 4, 4, "Ish soati", f"=SUM({rng(W)})", "#,##0", note="jami ishlangan")
    X.kpi(dash, 4, 6, "Norma", f"=SUM({rng(N)})", "#,##0", note="jadval bo'yicha")
    X.kpi(dash, 4, 8, "Bajarilish", "=IFERROR(D5/F5,0)", "0%", note="ish soati / norma")
    X.kpi(dash, 4, 10, "Kechikish", f"=SUM({rng(LT)})", note="kun (jami)", accent=X.RED)
    X.kpi(dash, 4, 12, "Belgilanmagan", f"=SUM({rng(UN)})", note="kun — tekshirish kerak", accent=X.MUTED)
    X.good_bad(dash, "H5", 0.95, 0.8)
    X.section(dash, 8, 2, "Bo'limlar bo'yicha ish soati")
    if depts:
        dash.add_chart(X.bar_chart("Ish soati / norma", ana, (2, a1, a2), [(5, a1, a2), (4, a1, a2)], [X.LINE, X.BLUE], "soat"),
                       "B9")
    X.section(dash, 25, 2, "Xulosalar")
    worked = sum(b[3 + nd] or 0 for b in body)
    norm = sum(b[4 + nd] or 0 for b in body)
    late_top = sorted(body, key=lambda b: -(b[6 + nd] or 0))
    X.notes(dash, 26, 2, 12, [
        f"Jami {worked:,.0f} soat ishlangan, norma {norm:,.0f} soat" + (f" ({round(100 * worked / norm)}%)." if norm else "."),
        (f"Eng ko'p kechikkan: {late_top[0][0]} — {late_top[0][6 + nd]} kun." if late_top and late_top[0][6 + nd] else
         "Kechikishlar qayd etilmagan."),
        "Belgilanmagan kunlar oylik hisoblanishidan oldin rahbar tomonidan tasdiqlanishi kerak.",
        "Kodlar va soatlar DETAILED DATA varag'ida; bo'limlar tahlili ANALYTICS varag'ida."])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def documents_digest(db: Session, scope: Scope, days: int = 30) -> str | None:
    docs = people.expiring_documents(db, scope, days)
    if not docs:
        return None
    lines = [f"{tg.e('calendar')} <b>{days} kun ichida muddati tugaydigan hujjatlar</b>", ""]
    for d in docs[:20]:
        when = "<b>MUDDATI O'TGAN</b>" if d["expired"] else f"{d['days_left']} kun"
        lines.append(f"• {_esc(d['full_name'])} ({_esc(d['branch'])}) — {_esc(d['title'])}: {when}")
    return "\n".join(lines)
