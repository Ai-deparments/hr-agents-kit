"""HR documents from templates -> PDF. Only real card data is filled in; anything unknown stays a blank line
'________' and is listed as missing (never invented). Salary goes in only for a payroll-allowed scope."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import cfg
from ..models import DocTemplate, Employee, HrDoc
from ..rbac import Scope, audit

BLANK = "________"
FIELD = re.compile(r"\{([a-z_]{2,30})\}")

DEFAULTS = [
    ("employment_certificate", "MA'LUMOTNOMA", "MA",
     "№ {number}                                                            {today}\n\n"
     "Ushbu ma'lumotnoma {full_name}ga berildi. U haqiqatan ham «{company}»da {hire_date} dan buyon "
     "{position} lavozimida ishlab kelmoqda.\n\n"
     "Ma'lumotnoma talab qilingan joyga taqdim etish uchun berildi.\n\n\n"
     "HR bo'limi rahbari  ______________  {hr_name}"),
    ("hire_order", "BUYRUQ — ishga qabul qilish to'g'risida", "B",
     "№ {number}                                                            {today}\n\n"
     "{full_name} {hire_date} dan boshlab {department} bo'limiga {position} lavozimiga "
     "{probation} sinov muddati bilan ishga qabul qilinsin.\n\n"
     "Asos: {full_name}ning arizasi.\n\n\n"
     "Rahbar  ______________  {director}\n\nBuyruq bilan tanishdim:  ______________  {full_name}"),
    ("leave_order", "BUYRUQ — mehnat ta'tili berish to'g'risida", "T",
     "№ {number}                                                            {today}\n\n"
     "{position} {full_name}ga {leave_from} dan {leave_to} gacha {leave_days} kalendar kunlik yillik mehnat ta'tili "
     "berilsin.\n\nAsos: {full_name}ning arizasi.\n\n\n"
     "Rahbar  ______________  {director}\n\nBuyruq bilan tanishdim:  ______________  {full_name}"),
]
PREFIX = {code: p for code, _, p, _ in DEFAULTS}


def ensure_templates(db: Session) -> None:
    have = set(db.scalars(select(DocTemplate.code)))
    for code, title, _, body in DEFAULTS:
        if code not in have:
            db.add(DocTemplate(code=code, title=title, body=body, updated_by="system"))
    db.flush()


def fields_of(body: str) -> list[str]:
    return list(dict.fromkeys(FIELD.findall(body)))


def _d(x: date | None) -> str | None:
    return x.strftime("%d.%m.%Y") if x else None


def _next_number(db: Session, code: str) -> str:
    y = date.today().year
    n = db.scalar(select(func.count(HrDoc.id)).where(HrDoc.template_code == code,
                                                   func.strftime("%Y", HrDoc.created_at) == str(y))) or 0
    return f"{PREFIX.get(code, 'H')}-{y}-{n + 1:03d}"


def render(db: Session, scope: Scope, tpl: DocTemplate, emp: Employee | None, extra: dict | None = None,
           number: str | None = None) -> tuple[str, list[str]]:
    vals: dict[str, str | None] = {
        "company": cfg("company.name"), "today": _d(date.today()), "number": number,
        "hr_name": cfg("documents.hr_name"), "director": cfg("documents.director"),
        "probation": cfg("documents.probation", "3 oylik"),
    }
    if emp:
        vals |= {"full_name": emp.full_name, "position": emp.position.title if emp.position else None,
                 "department": emp.department.name if emp.department else None,
                 "branch": emp.branch.name if emp.branch else None, "hire_date": _d(emp.hire_date), "phone": emp.phone}
        if scope.payroll and emp.base_salary:
            vals["salary"] = f"{emp.base_salary:,}".replace(",", " ") + " so'm"
    for k, v in (extra or {}).items():  # HR's own values win (e.g. leave dates)
        if v not in (None, ""):
            vals[k] = str(v)[:300]
    missing: list[str] = []

    def sub(m: re.Match) -> str:
        v = vals.get(m.group(1))
        if v in (None, ""):
            missing.append(m.group(1))
            return BLANK
        return str(v)
    return FIELD.sub(sub, tpl.body), list(dict.fromkeys(missing))


def issue(db: Session, scope: Scope, tpl: DocTemplate, emp: Employee | None, extra: dict | None = None) -> HrDoc:
    if emp and emp.branch_id and not scope.allows_branch(emp.branch_id):
        raise PermissionError("Not your branch")
    number = _next_number(db, tpl.code)
    body, missing = render(db, scope, tpl, emp, extra, number)
    doc = HrDoc(template_code=tpl.code, title=tpl.title, number=number, employee_id=emp.id if emp else None,
                body=body, missing=missing, created_by=scope.actor)
    db.add(doc)
    db.flush()
    audit(db, scope, "hr_doc_issue", f"hr_doc:{doc.id}", template=tpl.code, employee_id=emp.id if emp else None)
    return doc


_FONTS = [("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
          ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf")]


def pdf(doc: HrDoc) -> bytes:
    from fpdf import FPDF
    reg, bold = next(((r, b) for r, b in _FONTS if Path(r).exists() and Path(b).exists()), (None, None))
    if not reg:
        raise RuntimeError("No Unicode TTF font found for PDF (install fonts-dejavu-core)")
    p = FPDF(format="A4")
    p.set_margins(22, 20, 18)
    p.add_font("U", "", reg)
    p.add_font("U", "B", bold)
    p.add_page()
    p.set_font("U", "B", 11)
    p.cell(0, 6, str(cfg("company.name", "")), align="L", new_x="LMARGIN", new_y="NEXT")
    p.set_draw_color(15, 23, 42)
    p.line(22, p.get_y() + 1, 192, p.get_y() + 1)
    p.ln(10)
    p.set_font("U", "B", 14)
    p.multi_cell(0, 7, doc.title, align="C", new_x="LMARGIN", new_y="NEXT")
    p.ln(6)
    p.set_font("U", "", 11.5)
    p.multi_cell(0, 6.5, doc.body, new_x="LMARGIN", new_y="NEXT")
    return bytes(p.output())
