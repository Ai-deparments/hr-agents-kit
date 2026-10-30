"""KPI, ABC / 80-20 analytics, analytics settings and attached reports."""
from __future__ import annotations

import io
import re
import secrets
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require
from ..config import ROOT
from ..db import get_db
from ..models import Employee, KpiMetric, KpiValue, PayrollEntry, ReportFile
from ..rbac import Scope, audit
from ..services import kpi, payroll

router = APIRouter(prefix="/api/kpi")
UPLOADS = ROOT / "data" / "uploads" / "reports"
ALLOWED = {".xlsx", ".xls", ".csv", ".pdf", ".docx", ".pptx", ".png", ".jpg"}
MAX_FILE = 5 * 1024 * 1024
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _month(m: str | None) -> str:
    m = m or date.today().strftime("%Y-%m")
    if not MONTH.match(m):
        raise HTTPException(400, "Month must be YYYY-MM")
    return m


def _months_back(n: int, end: str) -> list[str]:
    y, m = map(int, end.split("-"))
    out = []
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def _writer(scope: Scope) -> None:
    if not (scope.can("analytics") or scope.can("payroll.write")):
        raise HTTPException(403, "Permission 'analytics' or 'payroll.write' required")


# ---------------- metrics ----------------

class MetricIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    unit: str = Field(default="", max_length=20)
    direction: str = Field(default="up", pattern=r"^(up|down)$")
    target: float = Field(gt=0)
    weight: int = Field(default=1, ge=1, le=100)
    position_id: int | None = None
    department_id: int | None = None
    active: bool = True


@router.get("/metrics")
def metrics(scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    return [kpi.metric_row(m) for m in db.scalars(select(KpiMetric).order_by(KpiMetric.active.desc(), KpiMetric.id))]


@router.post("/metrics")
def metric_create(body: MetricIn, scope: Scope = Depends(require("analytics")), db: Session = Depends(get_db)):
    m = KpiMetric(**body.model_dump())
    db.add(m)
    db.flush()
    audit(db, scope, "kpi_metric_create", f"kpi:{m.id}", name=m.name, target=m.target, weight=m.weight)
    db.commit()
    return kpi.metric_row(m)


@router.patch("/metrics/{mid}")
def metric_update(mid: int, body: MetricIn, scope: Scope = Depends(require("analytics")), db: Session = Depends(get_db)):
    m = db.get(KpiMetric, mid)
    if not m:
        raise HTTPException(404, "Not found")
    for k, v in body.model_dump().items():
        setattr(m, k, v)
    audit(db, scope, "kpi_metric_update", f"kpi:{m.id}", **body.model_dump())
    db.commit()
    return kpi.metric_row(m)


# ---------------- values ----------------

@router.get("/grid")
def grid(month: str | None = None, department_id: int | None = None, branch_id: int | None = None,
         scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    return kpi.grid(db, scope, _month(month), department_id, branch_id)


class ValueIn(BaseModel):
    employee_id: int
    metric_id: int
    value: float | None = None  # None clears the value


class ValuesIn(BaseModel):
    month: str
    values: list[ValueIn] = Field(max_length=2000)


@router.post("/values")
def values_save(body: ValuesIn, scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    _writer(scope)
    month = _month(body.month)
    if payroll.is_locked(db, month):
        raise HTTPException(409, "Month is closed — KPI values are frozen")
    changed = 0
    for v in body.values:
        e = db.get(Employee, v.employee_id)
        m = db.get(KpiMetric, v.metric_id)
        if not e or not m or not scope.allows_branch(e.branch_id):
            raise HTTPException(404, f"Employee {v.employee_id} or metric {v.metric_id} not found")
        if v.value is not None and not (0 <= v.value <= 1e12):
            raise HTTPException(400, "Value out of range")
        row = db.scalar(select(KpiValue).where(KpiValue.employee_id == e.id, KpiValue.metric_id == m.id, KpiValue.month == month))
        if v.value is None:
            if row:
                db.delete(row)
                changed += 1
            continue
        if row and row.value == v.value:
            continue
        if row:
            row.value, row.author = v.value, scope.actor
        else:
            db.add(KpiValue(employee_id=e.id, metric_id=m.id, month=month, value=v.value, author=scope.actor))
        changed += 1
    if changed:
        payroll.mark_changed(db, month)
        audit(db, scope, "kpi_values", month, changed=changed)
    db.commit()
    return {"changed": changed}


class ApplyIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@router.post("/{month}/apply")
def apply_to_payroll(month: str, body: ApplyIn, scope: Scope = Depends(require("payroll.write")), db: Session = Depends(get_db)):
    """A person moves KPI scores into the month's payroll (replaces earlier KPI entries of that month)."""
    month = _month(month)
    if payroll.is_locked(db, month):
        raise HTTPException(409, "Month is approved/closed")
    g = kpi.grid(db, scope, month)
    ids = [r["employee_id"] for r in g["rows"] if r["score"] is not None]
    for old in db.scalars(select(PayrollEntry).where(PayrollEntry.month == month, PayrollEntry.kind == "kpi",
                                                     PayrollEntry.cancelled.is_(False), PayrollEntry.employee_id.in_(ids or [-1]))):
        old.cancelled, old.cancel_reason = True, "replaced by KPI apply"
    n = 0
    for r in g["rows"]:
        if r["score"] is None:
            continue
        db.add(PayrollEntry(employee_id=r["employee_id"], month=month, kind="kpi", amount=round(r["score"]),
                            reason=f"KPI {month}: {r['filled']}/{r['applicable']} · {body.reason}"[:300], author=scope.actor))
        n += 1
    payroll.mark_changed(db, month)
    audit(db, scope, "kpi_apply", month, employees=n, reason=body.reason)
    db.commit()
    return {"applied": n, "skipped_no_kpi": len(g["rows"]) - n}


# ---------------- analytics ----------------

@router.get("/abc")
def abc(month: str | None = None, basis: str = "kpi", department_id: int | None = None,
        scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    if basis == "sales" and not scope.payroll:
        raise HTTPException(403, "Sales amounts need payroll visibility")
    try:
        return kpi.abc(db, scope, _month(month), basis, department_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/trend")
def trend(month: str | None = None, months: int = 6, department_id: int | None = None,
          scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    return kpi.trend(db, scope, _months_back(min(max(months, 2), 12), _month(month)), department_id)


@router.get("/sales")
def sales(month: str | None = None, branch_id: int | None = None,
          scope: Scope = Depends(require("analytics")), db: Session = Depends(get_db)):
    """Sales agents ranking (Smartup): amount, share, Δ vs previous month, ABC, 80/20."""
    from ..services import sales_kpi
    return sales_kpi.ranking(db, scope, _month(month), branch_id)


@router.get("/settings")
def settings_get(scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    return kpi.settings(db)


@router.put("/settings")
def settings_put(body: dict, scope: Scope = Depends(require("analytics")), db: Session = Depends(get_db)):
    try:
        v = kpi.save_settings(db, body)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    audit(db, scope, "analytics_settings", None, **v)
    db.commit()
    return v


@router.get("/excel")
def excel(month: str | None = None, department_id: int | None = None, scope: Scope = Depends(require("hr.read")),
          db: Session = Depends(get_db)):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    month = _month(month)
    g = kpi.grid(db, scope, month, department_id)
    a = kpi.abc(db, scope, month, "kpi", department_id)
    cls = {r["employee_id"]: r["class"] for r in a["rows"]}
    wb = Workbook()
    ws = wb.active
    ws.title = f"KPI {month}"
    head = ["Employee", "Branch", "Department", "Position"] + [f"{m['name']} ({m['unit']}) → {m['target']}" for m in g["metrics"]] + ["KPI %", "ABC"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in g["rows"]:
        ws.append([r["full_name"], r["branch"], r["department"], r["position"]]
                  + [r["values"].get(str(m["id"])) for m in g["metrics"]] + [r["score"], cls.get(r["employee_id"])])
    ws2 = wb.create_sheet("ABC")
    ws2.append(["#", "Employee", "KPI %", "Share %", "Cumulative %", "Class"])
    for r in a["rows"]:
        ws2.append([r["rank"], r["full_name"], r["value"], r["share"], r["cum_share"], r["class"]])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="kpi-{month}.xlsx"'})


# ---------------- attached reports ----------------

def _file_row(f: ReportFile) -> dict:
    return {"id": f.id, "title": f.title, "month": f.month, "kind": f.kind, "filename": f.filename, "size": f.size,
            "uploaded_by": f.uploaded_by, "created_at": f.created_at}


@router.get("/reports")
def reports(scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    return [_file_row(f) for f in db.scalars(select(ReportFile).order_by(ReportFile.id.desc()).limit(300))]


@router.post("/reports")
async def report_upload(file: UploadFile, title: str = "", month: str | None = None, kind: str = "other",
                        scope: Scope = Depends(require("analytics")), db: Session = Depends(get_db)):
    name = Path(file.filename or "report").name
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(400, f"Allowed: {', '.join(sorted(ALLOWED))}")
    if kind not in ("kpi", "abc", "payroll", "other"):
        raise HTTPException(400, "Bad kind")
    data = await file.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise HTTPException(413, "File too large (max 5 MB)")
    UPLOADS.mkdir(parents=True, exist_ok=True)
    path = UPLOADS / f"{secrets.token_hex(12)}{ext}"  # never trust the client file name on disk
    path.write_bytes(data)
    f = ReportFile(title=(title or name)[:200], month=_month(month) if month else None, kind=kind, filename=name[:200],
                   path=str(path), size=len(data), uploaded_by=scope.actor)
    db.add(f)
    db.flush()
    audit(db, scope, "report_upload", f"report:{f.id}", filename=name, size=len(data))
    db.commit()
    return _file_row(f)


@router.get("/reports/{rid}/download")
def report_download(rid: int, scope: Scope = Depends(require("hr.read")), db: Session = Depends(get_db)):
    f = db.get(ReportFile, rid)
    if not f or not Path(f.path).is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(f.path, filename=f.filename)


@router.delete("/reports/{rid}")
def report_delete(rid: int, scope: Scope = Depends(require("analytics")), db: Session = Depends(get_db)):
    f = db.get(ReportFile, rid)
    if not f:
        raise HTTPException(404, "Not found")
    Path(f.path).unlink(missing_ok=True)
    audit(db, scope, "report_delete", f"report:{f.id}", filename=f.filename)
    db.delete(f)
    db.commit()
    return {"ok": True}
