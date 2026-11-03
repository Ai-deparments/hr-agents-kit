"""Where every dashboard tile number comes from: the formula, the source systems and the rows behind it.
Uses the same functions as /api/dashboard, so the explanation always matches the tile."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AttendanceEvent, Candidate, Employee, ExternalRef, LeaveRequest, Registration
from ..config import cfg
from ..rbac import Scope
from . import analytics, attendance

SRC = {"timepay": "TimePay", "smartup": "Smartup"}
STATUS = {"present": "keldi", "late": "kechikdi", "on_shift": "smenada", "absent": "kelmadi", "leave": "ta'tilda",
          "unmarked": "belgilanmagan", "off": "dam olish", "needs_review": "tekshiruvda", "conflict": "ziddiyat",
          "untracked": "TimePay'da yo'q"}


def _active(db: Session, scope: Scope) -> list[Employee]:
    q = select(Employee).where(Employee.status != "fired")
    if scope.branch_ids is not None:
        q = q.where(Employee.branch_id.in_(scope.branch_ids or {-1}))
    return list(db.scalars(q.order_by(Employee.full_name)))


def _origin(db: Session, ids: list[int]) -> dict[int, str]:
    out: dict[int, str] = {}
    for r in db.scalars(select(ExternalRef).where(ExternalRef.kind == "employee", ExternalRef.local_id.in_(ids or [-1]))):
        out.setdefault(r.local_id, SRC.get(r.source, r.source))
    return out


def _last(db: Session, source: str):
    ts = db.scalar(select(func.max(AttendanceEvent.ts)).where(AttendanceEvent.source == source))
    return ts.isoformat(timespec="minutes") if ts else None


def active(db: Session, scope: Scope) -> dict:
    emps = _active(db, scope)
    org = _origin(db, [e.id for e in emps])
    t = analytics.turnover(db, scope, 3)
    return {
        "title": "Faol xodimlar", "value": len(emps),
        "formula": "Holati «ishdan bo'shatilgan» bo'lmagan barcha xodimlar (faol + sinov muddatida), sizning filiallaringiz bo'yicha.",
        "sources": [{"name": "TimePay", "detail": "import (ops jadvali bo'yicha), agar ulangan bo'lsa"},
                    {"name": "Smartup", "detail": "savdo agentlari importi, agar ulangan bo'lsa"},
                    {"name": "Panel / bot", "detail": "qo'lda qo'shilgan va botdan ro'yxatdan o'tganlar"}],
        "groups": [
            {"title": "Manba bo'yicha", "items": [{"label": k, "value": v} for k, v in
                                                 Counter(org.get(e.id, "Panel / bot") for e in emps).most_common()]},
            {"title": "Holati", "items": [{"label": {"active": "faol", "probation": "sinov muddatida"}.get(k, k), "value": v}
                                         for k, v in Counter(e.status for e in emps).most_common()]},
            {"title": "Bo'lim bo'yicha", "items": [{"label": k, "value": v} for k, v in
                                                  Counter(e.department.name if e.department else "Bo'limsiz" for e in emps).most_common()]},
        ],
        "rows_title": "Sinov muddatidagilar",
        "rows": [{"name": e.full_name, "info": e.position.title if e.position else "—",
                  "extra": f"ishga kirgan {e.hire_date:%d.%m.%Y}" if e.hire_date else ""} for e in emps if e.status == "probation"],
        "note": f"So'nggi 3 oyda ketgan: {t.get('left', 0)} kishi.",
    }


def shift(db: Session, scope: Scope) -> dict:
    d = attendance.day_summary(db, scope, date.today())
    rows = [r for r in d["rows"] if r["status"] not in ("off", "not_employed")]
    order = {"late": 0, "unmarked": 1, "absent": 2, "untracked": 3, "present": 4, "on_shift": 5}
    rows.sort(key=lambda r: (order.get(r["status"], 9), r["full_name"]))
    return {
        "title": "Bugun smenada", "value": f"{d['came']} / {d['scheduled']}",
        "formula": "Chap son — bugun kirish belgisi bor xodimlar. O'ng son — bugun jadval bo'yicha ishlashi kerak bo'lganlar "
                   "(dam olish kunidagilar kirmaydi). Kechikish — jadvaldagi boshlanish vaqtidan keyin kelganlar.",
        "sources": [{"name": "TimePay", "detail": "Face ID / turniket belgilari", "updated": _last(db, "timepay")},
                    {"name": "Ish jadvallari", "detail": "panel → Xodimlar → jadval"}],
        "groups": [{"title": "Bugun", "items": [{"label": STATUS.get(k, k), "value": v} for k, v in
                                               Counter(r["status"] for r in rows).most_common()]}],
        "rows_title": "Xodimlar",
        "rows": [{"name": r["full_name"], "info": STATUS.get(r["status"], r["status"]),
                  "extra": " · ".join(x for x in [f"keldi {r['check_in'][11:16]}" if r.get("check_in") else "",
                                                  f"{r['late_min']} daq kech" if r.get("late_min") else "", r["branch"]] if x)}
                 for r in rows][:80],
        "note": "«Belgilanmagan» — hali belgi yo'q, bu «kelmagan» degani emas.",
    }


def fund(db: Session, scope: Scope) -> dict:
    if not scope.payroll:
        return {"title": "Ish haqi fondi", "value": "—", "formula": "Oylik summalarini ko'rishga ruxsatingiz yo'q.",
                "sources": [], "groups": [], "rows": []}
    emps = _active(db, scope)
    known = [e for e in emps if e.base_salary]
    total = sum(e.base_salary for e in known)
    by_dep: dict[str, list[int]] = defaultdict(list)
    for e in known:
        by_dep[e.department.name if e.department else "Bo'limsiz"].append(e.base_salary)
    return {
        "title": "Ish haqi fondi", "value": total,
        "formula": "Faol xodimlarning asosiy oyliklari (oklad) yig'indisi. KPI, bonus, jarima va avans kirmaydi — "
                   "ular Oylik bo'limida hisoblanadi. O'rtacha = fond / oyligi kiritilgan xodimlar.",
        "sources": [{"name": "Xodim kartasi", "detail": "«Oklad» maydoni (panel yoki agent orqali)"}],
        "groups": [
            {"title": "Oylik kiritilgan", "items": [{"label": "kiritilgan", "value": len(known)},
                                                   {"label": "kiritilmagan", "value": len(emps) - len(known)}]},
            {"title": "Bo'lim bo'yicha (so'm)", "items": [{"label": k, "value": sum(v)} for k, v in
                                                         sorted(by_dep.items(), key=lambda kv: -sum(kv[1]))]},
        ],
        "rows_title": "Oyligi kiritilmaganlar",
        "rows": [{"name": e.full_name, "info": e.department.name if e.department else "Bo'limsiz", "extra": ""}
                 for e in emps if not e.base_salary][:80],
        "avg": round(total / len(known)) if known else None,
    }


def inbox(db: Session, scope: Scope) -> dict:
    regs = list(db.scalars(select(Registration).where(Registration.status == "pending"))) if scope.can("registrations") else []
    cands = list(db.scalars(select(Candidate).where(Candidate.status == "new")))
    q = select(LeaveRequest).join(Employee).where(LeaveRequest.status == "pending")
    if scope.branch_ids is not None:
        q = q.where(Employee.branch_id.in_(scope.branch_ids or {-1}))
    reqs = list(db.scalars(q))
    return {
        "title": "Botdan arizalar", "value": len(regs),
        "formula": "Katta son — botda «Men xodimman» deb ro'yxatdan o'tib, tasdiq kutayotganlar. Pastda — intervyudan o'tgan "
                   "yangi nomzodlar va xodimlarning ko'rib chiqilmagan so'rovlari (ta'til, ma'lumotnoma va h.k.).",
        "sources": [{"name": "Telegram bot", "detail": cfg("company.recruiter_bot", "") or "HR bot"}],
        "groups": [{"title": "Kutmoqda", "items": [{"label": "ro'yxatdan o'tish", "value": len(regs)},
                                                   {"label": "yangi nomzod", "value": len(cands)},
                                                   {"label": "xodim so'rovi", "value": len(reqs)}]}],
        "rows_title": "Ro'yxat",
        "rows": [{"name": r.full_name, "info": "ro'yxatdan o'tish", "extra": ""} for r in regs]
        + [{"name": c.full_name, "info": "nomzod", "extra": f"ball {c.score}" if c.score is not None else ""} for c in cands]
        + [{"name": r.employee.full_name, "info": f"so'rov: {r.kind}",
            "extra": f"{r.date_from:%d.%m}" if r.date_from else ""} for r in reqs],
    }


TILES = {"active": active, "shift": shift, "fund": fund, "inbox": inbox}
