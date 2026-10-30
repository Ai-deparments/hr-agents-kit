"""One report per forum topic, written for a phone screen: a heading, 3-5 key lines, short lists — no wide tables.
A report with nothing worth saying returns None and is not sent."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (Candidate, CandidateStep, Employee, InterviewSlot, MaterialSend, OnboardingMaterial, PayrollEntry,
                      Vacancy)
from ..rbac import Scope
from . import analytics, tg, weekly

M, E = tg.md, tg.me


def _li(items: list[str], limit: int = 10) -> str:
    more = f"\n- … yana {len(items) - limit}" if len(items) > limit else ""
    return "\n".join(f"- {x}" for x in items[:limit]) + more


def _som(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " so'm"


def _day(d: date) -> tuple[datetime, datetime]:
    a = datetime.combine(d, datetime.min.time())
    return a, a + timedelta(days=1)


def recruiting_md(db: Session, scope: Scope, today: date | None = None, evening: bool = False) -> str | None:
    """Morning: yesterday's candidates + today's interviews. Evening: today's results + tomorrow's interviews."""
    today = today or date.today()
    a, b = _day(today if evening else today - timedelta(days=1))
    sa, sb = _day(today + timedelta(days=1) if evening else today)
    new = list(db.scalars(select(Candidate).where(Candidate.created_at >= a, Candidate.created_at < b).order_by(Candidate.score.desc())))
    slots = list(db.scalars(select(InterviewSlot).where(InterviewSlot.status == "booked", InterviewSlot.starts_at >= sa,
                                                        InterviewSlot.starts_at < sb).order_by(InterviewSlot.starts_at)))
    offers = list(db.scalars(select(CandidateStep).where(CandidateStep.kind == "offer", CandidateStep.status == "open")))
    answered = list(db.scalars(select(CandidateStep).where(CandidateStep.kind == "offer", CandidateStep.answered_at >= a,
                                                           CandidateStep.answered_at < b))) if evening else []
    vac = analytics.vacancies_sla(db, scope, today)
    late = [v for v in vac if v.get("light") == "red"]
    drafts = list(db.scalars(select(Vacancy).where(Vacancy.status == "draft", Vacancy.is_template.is_(False))))
    if evening and not (new or slots or answered):
        return None  # the evening note only when the day brought something
    if not (new or slots or offers or late or drafts):
        return None
    when, sday = ("bugun", "Ertangi") if evening else ("kecha", "Bugungi")
    lines = [f"Yangi nomzod ({when}): **{len(new)}**", f"{sday} suhbat: **{len(slots)}**"]
    if evening:
        lines.append(f"Taklifga javob: **{len(answered)}**")
    else:
        lines += [f"Ochiq vakansiya: **{len(vac)}**" + (f", muddati o'tgan: **{len(late)}**" if late else ""),
                  f"Javob kutilayotgan taklif: **{len(offers)}**"] + ([f"Qoralama: **{len(drafts)}**"] if drafts else [])
    out = [f"## {E('moon' if evening else 'briefcase')} Rekruting — {today:%d.%m}, {'kech' if evening else 'ertalab'}", _li(lines)]
    if slots:
        out += [f"### {E('clock')} {sday} suhbatlar", _li([
            f"`{s.starts_at:%H:%M}` {M(db.get(Candidate, s.candidate_id).full_name if s.candidate_id else '—')}"
            + (f" · {M(s.place)}" if s.place else "") for s in slots])]
    if new:
        out += [f"### {E('user')} Yangi nomzodlar", _li([
            f"{M(c.full_name)} — {M(c.vacancy.title) if c.vacancy else '—'}" + (f" · **{c.score}**" if c.score is not None else "")
            for c in new], 8)]
    if answered:
        out += [f"### {E('check')} Taklif javoblari", _li([
            f"{M(st.candidate.full_name)} — {'qabul qildi' if st.status == 'done' else 'rad etdi'}" for st in answered])]
    if late and not evening:
        out += [f"### {E('warning')} Muddati o'tgan vakansiyalar", _li([f"{M(v['title'])} — {v['days_open']} kun" for v in late], 5)]
    out += [f"#### {E('idea')} *Nomzodlar baholari — panelda, qarorni HR qiladi.*"]
    return "\n\n".join(out)


def onboarding_md(db: Session, scope: Scope, today: date | None = None, evening: bool = False) -> str | None:
    """Morning: today's talks, unseen materials, newcomers. Evening: what was sent / viewed today + tomorrow's talks."""
    today = today or date.today()
    a, b = _day(today if evening else today - timedelta(days=1))
    ta, tb = _day(today + timedelta(days=1) if evening else today)
    newbies = [e for e in db.scalars(select(Employee).where(Employee.status == "probation"))
               if not e.branch_id or scope.allows_branch(e.branch_id)]
    sent = list(db.scalars(select(MaterialSend).where(MaterialSend.sent_at >= a, MaterialSend.sent_at < b, MaterialSend.queued.is_(True))))
    viewed = list(db.scalars(select(MaterialSend).where(MaterialSend.viewed_at >= a, MaterialSend.viewed_at < b)))
    unseen = list(db.scalars(select(MaterialSend).where(MaterialSend.queued.is_(True), MaterialSend.viewed_at.is_(None),
                                                        MaterialSend.sent_at < _day(today)[0] - timedelta(days=2))))
    talks = list(db.scalars(select(MaterialSend).where(MaterialSend.talk_done.is_(False), MaterialSend.talk_at >= ta,
                                                       MaterialSend.talk_at < tb).order_by(MaterialSend.talk_at)))
    from .onboarding import waiting as waiting_list
    waiting = [] if evening else waiting_list(db, scope, today)  # hired, card + plan not started yet
    if evening and not (sent or viewed or talks):
        return None
    if not (newbies or sent or unseen or talks or waiting):
        return None
    title = {m.id: m.title for m in db.scalars(select(OnboardingMaterial))}
    when, tday = ("bugun", "Ertangi") if evening else ("kecha", "Bugungi")
    lines = ([] if evening else [f"Sinov muddatidagi xodim: **{len(newbies)}**", f"Ishga olingan, boshlash kutilmoqda: **{len(waiting)}**"]) + [
        f"Yuborilgan material ({when}): **{len(sent)}**", f"Ko'rildi ({when}): **{len(viewed)}**"]
    lines += ([] if evening else [f"2+ kun ko'rilmagan: **{len(unseen)}**"]) + [f"{tday} suhbat: **{len(talks)}**"]
    out = [f"## {E('moon' if evening else 'target')} Onboarding — {today:%d.%m}, {'kech' if evening else 'ertalab'}", _li(lines)]
    if talks:
        out += [f"### {E('clock')} {tday} suhbatlar", _li([
            f"`{t.talk_at:%H:%M}` {M(t.employee.full_name)} — {M(title.get(t.material_id, '—'))}"
            + (f" · {M(t.talk_with)}" if t.talk_with else "") for t in talks])]
    if unseen and not evening:
        per = Counter(s.employee.full_name for s in unseen)
        out += [f"### {E('eyes')} Ko'rmaganlar", _li([f"{M(n)} — {k} ta material" for n, k in per.most_common()], 8)]
    if waiting:  # count only in the group; names are in the panel (Onboarding -> waiting)
        oldest = max(w["days_waiting"] for w in waiting)
        out += [f"#### {E('clock')} *{len(waiting)} ta ishga olingan nomzod kartasi ochilmagan (eng uzoq: {oldest} kun) — panelda boshlang.*"]
    if newbies and not evening:
        out += [f"### {E('user')} Yangi xodimlar", _li([
            f"{M(e.full_name)} — {M(e.position.title) if e.position else '—'}"
            + (f" · {(today - e.hire_date).days}-kun" if e.hire_date else "") for e in newbies], 8)]
    return "\n\n".join(out)


def payroll_md(db: Session, scope: Scope, today: date | None = None, evening: bool = False) -> str | None:
    """Morning: month to date. Evening: only today's new entries (nothing new -> no message)."""
    today = today or date.today()
    month = today.strftime("%Y-%m")
    q = select(PayrollEntry).where(PayrollEntry.month == month, PayrollEntry.cancelled.is_(False))
    if evening:
        a, b = _day(today)
        q = q.where(PayrollEntry.created_at >= a, PayrollEntry.created_at < b)
    emps = {e.id: e for e in db.scalars(select(Employee))}
    rows = [p for p in db.scalars(q) if p.employee_id in emps
            and (not emps[p.employee_id].branch_id or scope.allows_branch(emps[p.employee_id].branch_id))]
    if not rows:
        return None
    tot, per_pen = defaultdict(int), defaultdict(int)
    for p in rows:
        tot[p.kind] += p.amount if p.kind != "kpi" else 0
        if p.kind == "penalty":
            per_pen[p.employee_id] += p.amount
    names = {"penalty": "Jarima", "bonus": "Bonus", "advance": "Avans", "other": "Ushlanma / boshqa"}
    head = f"Oylik — bugungi yozuvlar, {today:%d.%m}" if evening else f"Oylik — {month}, {today:%d.%m} holatiga"
    out = [f"## {E('money')} {head}", _li([f"{names[k]}: **{_som(tot[k])}**" for k in names if tot.get(k)] or ["Yozuvlar yo'q"])]
    if per_pen:
        top = sorted(per_pen.items(), key=lambda x: -x[1])[:5]
        out += [f"### {E('warning')} " + ("Jarimalar" if evening else "Eng ko'p jarima"),
                _li([f"{M(emps[i].full_name)} — {_som(v)}" for i, v in top])]
    out += [f"#### {E('idea')} *Manba: TimePay va panel. Hisob-kitob va to'lovni faqat odam tasdiqlaydi.*"]
    return "\n\n".join(out)


def analytics_md(db: Session, scope: Scope, today: date | None = None) -> str | None:
    today = today or date.today()
    last_monday = today - timedelta(days=today.weekday() + 7)
    weeks = []
    for i in range(3, -1, -1):
        w = weekly.week_data(db, scope, last_monday - timedelta(weeks=i))
        s, c = sum(x["sched"] for x in w["days"]), sum(x["came"] for x in w["days"])
        weeks.append((w["monday"], c, s, sum(x["late"] for x in w["days"]), w))
    if not any(s for _, _, s, _, _ in weeks):
        return None
    cur = weeks[-1]
    disc = defaultdict(lambda: [0, 0])
    for *_, w in weeks:
        for p in w["people"]:
            disc[p["name"]][0] += p["late"]
            disc[p["name"]][1] += p["late_min"]
    worst = sorted(((n, d, m) for n, (d, m) in disc.items() if d), key=lambda x: (-x[1], -x[2]))[:5]
    t = analytics.turnover(db, scope, 3, "department", today)
    out = [f"## {E('chart')} HR tahlil — 4 hafta",
           _li([f"{m:%d.%m}: davomat **{round(100 * c / s) if s else '—'}%**, kechikish **{l}**" for m, c, s, l, _ in weeks]),
           f"### {E('warning')} Intizom (4 hafta)", _li([f"{M(n)} — {d} kun, {m} daq" for n, d, m in worst]) if worst else "- Kechikish yo'q",
           f"### {E('chart_down')} Kadrlar oqimi (3 oy)",
           _li([f"Ketdi: **{t['left']}** / {t['base']} ({t['rate'].split(' (')[0]})", f"Birinchi 30 kunda ketgan: **{t['left_first_30_days']}**"])]
    prev = weeks[-2]
    if cur[2] and prev[2]:
        d = round(100 * cur[1] / cur[2]) - round(100 * prev[1] / prev[2])
        out += [f"#### {E('idea')} *O'tgan haftaga nisbatan davomat {'+' if d >= 0 else ''}{d} p.p.*"]
    return "\n\n".join(out)


def analytics_evening_md(db: Session, scope: Scope, today: date | None = None) -> str | None:
    """Evening: today against the 4-week average for the same weekday + week-to-date discipline."""
    today = today or date.today()
    from . import attendance as att
    t = att.day_summary(db, scope, today)
    if not t["scheduled"]:
        return None
    past = [att.day_summary(db, scope, today - timedelta(weeks=i)) for i in range(1, 5)]
    rates = [p["came"] / p["scheduled"] for p in past if p["scheduled"]]
    avg = round(100 * sum(rates) / len(rates)) if rates else None
    now = round(100 * t["came"] / t["scheduled"])
    w = weekly.week_data(db, scope, today - timedelta(days=today.weekday()))
    worst = [p for p in w["people"] if p["late"]][:5]
    out = [f"## {E('chart')} HR tahlil — {today:%d.%m}, kun yakuni",
           _li([f"Bugun davomat: **{now}%**" + (f" (shu kun, 4 hafta o'rtacha: {avg}%)" if avg is not None else ""),
                f"Kechikish: **{t['late']}**", f"Belgilanmagan: **{t['unmarked']}**"])]
    if worst:
        out += [f"### {E('warning')} Hafta boshidan kechikkanlar", _li([f"{M(p['name'])} — {p['late']} kun, {p['late_min']} daq" for p in worst])]
    if avg is not None and now < avg - 10:
        out += [f"#### {E('idea')} *Bugun o'rtachadan {avg - now} p.p. past — sababini bo'lim rahbarlaridan so'rang.*"]
    return "\n\n".join(out)


SIGNAL_UZ = {"late": "kechikish", "absent": "tasdiqlangan kelmaslik", "early_leave": "erta ketish"}


def weekly_signals_md(db: Session, scope: Scope, today: date | None = None, private: bool = False) -> str | None:
    """Weekly per-branch signals. The group gets one count line; branch names and numbers only in private chats."""
    w = analytics.weekly_signals(db, scope, today)
    n = len(w["signals"])
    if not n:
        return None
    a, b = w["period"].split("..")
    period = f"{date.fromisoformat(a):%d.%m}–{date.fromisoformat(b):%d.%m}"
    if not private:
        return (f"## {E('chart_up')} Haftalik signallar — {period}\n\n"
                f"- Filial signallari: **{n}** (kechikish / kelmaslik / erta ketish odatdagidan 2× ko'p)\n\n"
                f"#### {E('idea')} *Tafsilotlar shaxsiy xabarda yuborildi.*")
    return "\n\n".join([
        f"## {E('chart_up')} Haftalik signallar — {period}",
        _li([f"{M(s['branch'])}: {SIGNAL_UZ[s['metric']]} **{s['last_7_days']}** (odatdagi hafta: {s['usual_week']})"
             for s in w["signals"]], 20),
        f"#### {E('idea')} *Qoida: oxirgi 7 kun ≥ 3 holat va oldingi 4 hafta o'rtachasidan ≥ 2×. "
        f"Belgilanmagan kun kelmaslik hisoblanmaydi. Gaplashish uchun sabab — qaror emas.*"])
