"""Changes HR asks the agent for in words: employee card fields and payroll entries.
Two steps: `propose` shows the diff and parks it; `confirm` applies it only from a LATER message of the same person
(a different agent run), so the model can never propose and apply in one go."""
from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Branch, Department, Employee, PayrollEntry, Position, Setting
from ..rbac import Scope, audit
from . import payroll
from .people import norm_name, search_employees

TTL = timedelta(minutes=15)
EMP_FIELDS = ("status", "position", "department", "branch", "phone", "hire_date", "base_salary", "pay_type",
              "schedule_code", "leave_balance_days")
ENTRY_KINDS = {"advance", "bonus", "penalty", "warning", "kpi", "other"}
STATUS_UZ = {"probation": "sinov muddatida", "active": "faol (sinovsiz)"}


class EditError(ValueError):
    """Safe to show to the person."""


def _write_ok(scope: Scope, perm: str) -> bool:
    if scope.perms:  # panel user: its own role permissions
        return scope.can(perm) or scope.can("hr.write")
    return scope.at_least("hr_head")  # bot: HR head and owner


def find_employee(db: Session, scope: Scope, who: str) -> Employee:
    w = (who or "").strip().lstrip("#")
    if w.isdigit():
        e = db.get(Employee, int(w))
        if e and e.status != "fired" and scope.allows_branch(e.branch_id):
            return e
        raise EditError(f"Xodim #{w} topilmadi")
    found = search_employees(db, scope, w, limit=6)
    if not found:
        raise EditError(f"'{who}' topilmadi")
    if len(found) > 1:
        names = "; ".join(f"#{x['id']} {x['full_name']} ({x['position'] or '—'}, {x['branch'] or '—'})" for x in found)
        raise EditError(f"Bir nechta xodim mos keldi, qaysi biri? {names}")
    return db.get(Employee, found[0]["id"])


def _pick(db: Session, model, attr: str, text: str, label: str):
    n = norm_name(text)
    rows = list(db.scalars(select(model)))
    exact = [r for r in rows if norm_name(getattr(r, attr)) == n]
    hits = exact or [r for r in rows if n and n in norm_name(getattr(r, attr))]
    if len(hits) == 1:
        return hits[0]
    opts = ", ".join(sorted({getattr(r, attr) for r in (hits or rows)}))[:600]
    raise EditError(f"{label} '{text}' aniq emas. Variantlar: {opts}")


def _show(e: Employee, field: str):
    return {"status": STATUS_UZ.get(e.status, e.status), "position": e.position.title if e.position else None,
            "department": e.department.name if e.department else None, "branch": e.branch.name if e.branch else None,
            "hire_date": e.hire_date.isoformat() if e.hire_date else None}.get(field, getattr(e, field, None))


def _employee_changes(db: Session, scope: Scope, e: Employee, ask: dict) -> list[dict]:
    out = []
    for f in EMP_FIELDS:
        v = ask.get(f)
        if v in (None, ""):
            continue
        if f == "status":
            v = {"faol": "active", "active": "active", "sinov": "probation", "probation": "probation"}.get(str(v).lower(), str(v))
            if v not in ("active", "probation"):
                raise EditError("Status faqat 'active' (sinovsiz) yoki 'probation'. Ishdan bo'shatish — panelda, sabab bilan.")
            new, shown = v, STATUS_UZ[v]
        elif f in ("position", "department", "branch"):
            model, attr, label = {"position": (Position, "title", "Lavozim"), "department": (Department, "name", "Bo'lim"),
                                  "branch": (Branch, "name", "Filial")}[f]
            obj = _pick(db, model, attr, str(v), label)
            if f == "branch" and not scope.allows_branch(obj.id):
                raise EditError("Bu filial sizning ruxsatingizda emas")
            new, shown = obj.id, getattr(obj, attr)
        elif f == "base_salary":
            if not scope.payroll:
                raise EditError("Oylikni o'zgartirishga ruxsat yo'q")
            new = int(v)
            if not 0 <= new <= 1_000_000_000:
                raise EditError("Oylik summasi noto'g'ri")
            shown = new
        elif f == "hire_date":
            new = date.fromisoformat(str(v)).isoformat()
            shown = new
        elif f == "leave_balance_days":
            new = shown = float(v)
        else:
            new = shown = str(v)[:60]
        old = _show(e, f)
        if old != shown:
            out.append({"field": f, "from": old, "to": shown, "value": new})
    return out


def propose(db: Session, scope: Scope, run_id: str, who: str, fields: dict | None = None, entry: dict | None = None) -> dict:
    e = find_employee(db, scope, who)
    if not scope.allows_branch(e.branch_id):
        raise EditError("Bu xodim sizning filiallaringizda emas")
    change = {"employee_id": e.id, "run_id": run_id, "expires": (datetime.now() + TTL).isoformat(timespec="seconds")}
    if entry:
        kind = entry.get("kind")
        if kind not in ENTRY_KINDS:
            raise EditError(f"Turi: {', '.join(sorted(ENTRY_KINDS))}")
        if not _write_ok(scope, "payroll.write"):
            raise EditError("Oylik yozuvlarini kiritishga ruxsat yo'q")
        amount = int(entry.get("amount") or 0)
        if kind in ("advance", "bonus", "penalty", "other") and not scope.payroll:
            raise EditError("Pul summalarini kiritishga ruxsat yo'q")
        if not 0 <= amount <= 100_000_000 or (kind == "kpi" and amount > 120):
            raise EditError("Summa noto'g'ri")
        month = entry.get("month") or date.today().strftime("%Y-%m")
        if payroll.is_locked(db, month) and kind != "warning":
            raise EditError(f"{month} oyi yopilgan — pul yozuvlari kiritilmaydi")
        reason = (entry.get("reason") or "").strip()
        if len(reason) < 3:
            raise EditError("Sababini yozing (kamida 3 harf)")
        change["entry"] = {"kind": kind, "amount": amount, "month": month, "reason": reason[:300]}
        summary = [{"field": kind, "from": None, "to": f"{amount} · {month} · {reason[:80]}"}]
    else:
        if not _write_ok(scope, "hr.write"):
            raise EditError("Xodim kartasini o'zgartirishga ruxsat yo'q")
        diff = _employee_changes(db, scope, e, fields or {})
        if not diff:
            raise EditError("O'zgaradigan narsa yo'q (qiymatlar hozirgisi bilan bir xil)")
        change["fields"] = {d["field"]: d["value"] for d in diff}
        summary = [{k: d[k] for k in ("field", "from", "to")} for d in diff]
    change["id"] = secrets.token_hex(3)
    db.merge(Setting(key=f"pending_edit:{scope.actor}", value=change))
    db.commit()
    return {"change_id": change["id"], "employee": f"#{e.id} {e.full_name}", "changes": summary}


def confirm(db: Session, scope: Scope, run_id: str, change_id: str = "") -> dict:
    s = db.get(Setting, f"pending_edit:{scope.actor}")
    ch = s.value if s else None
    if not ch or (change_id and ch.get("id") != change_id):
        raise EditError("Tasdiqlanadigan o'zgarish topilmadi — avval o'zgarishni so'rang")
    if ch["run_id"] == run_id:
        raise EditError("Tasdiq odamning keyingi xabaridan keladi: avval o'zgarishni ko'rsating va 'ha' ni kuting")
    if datetime.fromisoformat(ch["expires"]) < datetime.now():
        db.delete(s)
        db.commit()
        raise EditError("Muddati o'tdi (15 daqiqa) — qaytadan so'rang")
    e = db.get(Employee, ch["employee_id"])
    if not e or not scope.allows_branch(e.branch_id):
        raise EditError("Xodim topilmadi")
    if ent := ch.get("entry"):
        if payroll.is_locked(db, ent["month"]) and ent["kind"] != "warning":
            raise EditError("Oy yopilgan")
        db.add(PayrollEntry(employee_id=e.id, author=scope.actor, **ent))
        payroll.mark_changed(db, ent["month"])
        audit(db, scope, "payroll_entry", f"employee:{e.id}", kind=ent["kind"], amount=ent["amount"], reason=ent["reason"], via="agent")
        done = f"{ent['kind']} {ent['amount']} ({ent['month']})"
    else:
        f = ch["fields"]
        for k, v in f.items():
            if k == "position":
                e.position_id = v
            elif k == "department":
                e.department_id = v
            elif k == "branch":
                e.branch_id = v
            elif k == "hire_date":
                e.hire_date = date.fromisoformat(v)
            else:
                setattr(e, k, v)
        audit(db, scope, "employee_update", f"employee:{e.id}", fields=sorted(f), via="agent")
        done = ", ".join(sorted(f))
    db.delete(s)
    db.commit()
    return {"applied": True, "employee": f"#{e.id} {e.full_name}", "done": done}


def cancel(db: Session, scope: Scope, run_id: str) -> dict:
    s = db.get(Setting, f"pending_edit:{scope.actor}")
    if s:
        db.delete(s)
        db.commit()
    return {"cancelled": bool(s)}


def pay_for(db: Session, scope: Scope, who: str, month: str | None = None) -> dict:
    e = find_employee(db, scope, who)
    month = month or date.today().strftime("%Y-%m")
    t = payroll.payroll_table(db, scope, month)
    row = next((r for r in t["rows"] if r.get("employee_id") == e.id), None)
    if row is None:
        return {"employee": f"#{e.id} {e.full_name}", "month": month,
                "error": "Bu oy tabelida yo'q (jadval yoki ishga kirgan sana tekshirilsin)"}
    keep = ("base", "norm_hours", "worked_hours", "accrued", "kpi", "bonus", "sales_bonus", "allowances", "penalty",
            "late_penalty", "advance", "other", "total", "known", "explain")
    return {"employee": f"#{e.id} {e.full_name}", "month": month, "status": t["status"],
            **{k: row.get(k) for k in keep if k in row}}
