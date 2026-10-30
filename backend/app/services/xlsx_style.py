"""House style for Excel reports (excel-report-design skill): DASHBOARD / DETAILED DATA / ANALYTICS,
navy-blue palette, Aptos, KPI tiles, banded tables, real formulas, charts."""
from __future__ import annotations

from openpyxl.chart import BarChart, Reference
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

NAVY, BLUE, BG, GREEN, RED, TEXT, MUTED, LINE, WHITE = ("0F172A", "2563EB", "F8FAFC", "10B981", "EF4444", "334155",
                                                       "64748B", "E2E8F0", "FFFFFF")
FONT = "Aptos"
thin = Side(style="thin", color=LINE)


def f(size=10.5, bold=False, color=TEXT, italic=False) -> Font:
    return Font(name=FONT, size=size, bold=bold, color=color, italic=italic)


def fill(hex_: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_)


def sheet(ws: Worksheet, widths: dict[str, float]) -> None:
    ws.sheet_view.showGridLines = False
    for col, w in widths.items():
        ws.column_dimensions[col].width = w


def title(ws: Worksheet, text: str, sub: str, span: int) -> None:
    ws.row_dimensions[1].height = 34
    ws.row_dimensions[2].height = 20
    c = ws.cell(1, 2, text)
    c.font = f(22, True, NAVY)
    c.alignment = Alignment(vertical="center")
    s = ws.cell(2, 2, sub)
    s.font = f(11, color=MUTED)
    ws.merge_cells(start_row=1, start_column=2, end_row=1, end_column=span)
    ws.merge_cells(start_row=2, start_column=2, end_row=2, end_column=span)


def section(ws: Worksheet, row: int, col: int, text: str) -> None:
    c = ws.cell(row, col, text)
    c.font = f(13, True, NAVY)
    ws.row_dimensions[row].height = 22


def kpi(ws: Worksheet, row: int, col: int, label: str, formula: str, fmt: str = "#,##0", note: str = "",
        accent: str = BLUE) -> None:
    """Tile = 2 merged columns × 3 rows: label / big value / note."""
    for r in range(row, row + 3):
        for cc in (col, col + 1):
            ws.cell(r, cc).fill = fill(WHITE)
            ws.cell(r, cc).border = Border(top=thin if r == row else None, bottom=thin if r == row + 2 else None,
                                           left=thin if cc == col else None, right=thin if cc == col + 1 else None)
    for r in range(row, row + 3):
        ws.merge_cells(start_row=r, start_column=col, end_row=r, end_column=col + 1)
    lab = ws.cell(row, col, label)
    lab.font = f(10, True, MUTED)
    lab.alignment = Alignment(indent=1, vertical="bottom")
    v = ws.cell(row + 1, col, formula)
    v.font = f(24, True, accent)
    v.number_format = fmt
    v.alignment = Alignment(indent=1, vertical="center")
    n = ws.cell(row + 2, col, note)
    n.font = f(9, color=MUTED)
    n.alignment = Alignment(indent=1, vertical="top", wrap_text=True)
    ws.row_dimensions[row + 1].height = 34


def table(ws: Worksheet, top: int, left: int, headers: list[str], rows: list[list], formats: dict[int, str] | None = None,
          filter_=True, freeze=True) -> tuple[int, int]:
    """Navy header, banded rows, thin separators, autofilter, frozen header. Returns (first_data_row, last_data_row)."""
    formats = formats or {}
    for j, h in enumerate(headers):
        c = ws.cell(top, left + j, h)
        c.font = f(10.5, True, WHITE)
        c.fill = fill(NAVY)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[top].height = 30
    for i, row in enumerate(rows):
        r = top + 1 + i
        for j, v in enumerate(row):
            c = ws.cell(r, left + j, v)
            c.font = f()
            c.border = Border(bottom=thin)
            if i % 2:
                c.fill = fill(BG)
            if j in formats:
                c.number_format = formats[j]
            numeric = isinstance(v, (int, float)) or (isinstance(v, str) and v.startswith("="))
            c.alignment = Alignment(horizontal="right" if numeric else "left", indent=1, vertical="center")
    last = top + max(len(rows), 1)
    if filter_ and rows:
        ws.auto_filter.ref = f"{get_column_letter(left)}{top}:{get_column_letter(left + len(headers) - 1)}{last}"
    if freeze:
        ws.freeze_panes = ws.cell(top + 1, left)
    return top + 1, last


def good_bad(ws: Worksheet, rng: str, good_at: float, bad_below: float) -> None:
    ws.conditional_formatting.add(rng, CellIsRule(operator="greaterThanOrEqual", formula=[str(good_at)],
                                                  font=Font(name=FONT, bold=True, color=GREEN)))
    ws.conditional_formatting.add(rng, CellIsRule(operator="lessThan", formula=[str(bad_below)],
                                                  font=Font(name=FONT, bold=True, color=RED)))


def bar_chart(title_: str, data_ws: Worksheet, cats: tuple[int, int, int], series: list[tuple[int, int, int]],
              colors: list[str], y_title: str = "") -> BarChart:
    """cats/series = (col, first_row, last_row); series header is the row above first_row."""
    ch = BarChart()
    ch.type, ch.style, ch.title, ch.height, ch.width = "col", 10, title_, 7.5, 16
    ch.y_axis.title = y_title
    ch.y_axis.majorGridlines = None
    for (col, r1, r2), color in zip(series, colors):
        ch.add_data(Reference(data_ws, min_col=col, min_row=r1 - 1, max_row=r2), titles_from_data=True)
        s = ch.series[-1]
        s.graphicalProperties.solidFill = color
        s.graphicalProperties.line.solidFill = color
    ch.set_categories(Reference(data_ws, min_col=cats[0], min_row=cats[1], max_row=cats[2]))
    ch.legend.position = "b"
    return ch


def notes(ws: Worksheet, row: int, col: int, span: int, items: list[str]) -> int:
    for i, t in enumerate(items):
        c = ws.cell(row + i, col, f"•  {t}")
        c.font = f(10.5)
        c.alignment = Alignment(wrap_text=True, vertical="top", indent=1)
        ws.merge_cells(start_row=row + i, start_column=col, end_row=row + i, end_column=col + span - 1)
        ws.row_dimensions[row + i].height = 30
    return row + len(items)
