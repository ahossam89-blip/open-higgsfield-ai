"""Parametric generator for Arabic-language planner low-content books
(weekly or monthly), driven by the `spec` block of a books.yaml entry.

spec fields (all but `kind`/`year` optional):
    kind:                  "weekly" | "monthly"
    year:                  int, e.g. 2026
    start_month, end_month: 1-12, defaults 1..12
    week_start:            "saturday" | "sunday" | "monday" (default "saturday")
    style:                 "minimal" | "bold"  (controls accent color/weight)
    include_habit_tracker: bool
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
from pathlib import Path

import yaml

from common import kdp_specs
from lowcontent.common.pdf_render import svg_pages_to_pdf
from lowcontent.common.svg_utils import (
    ARABIC_HEADING_FONT_STACK,
    ARABIC_MONTHS,
    ARABIC_WEEKDAYS,
    SvgPage,
    page_size_pt,
    to_arabic_indic_digits,
)

WEEKDAY_STARTS = {"sunday": 6, "monday": 0, "saturday": 5}  # Python calendar: Mon=0..Sun=6

STYLE_ACCENTS = {
    "minimal": {"accent": "#2b2b2b", "grid": "#dcdcdc", "fill": "#f7f7f5"},
    "bold": {"accent": "#0f6b5c", "grid": "#c7ded9", "fill": "#eef7f5"},
}


def _ordered_weekdays(week_start: str) -> list[int]:
    """Return weekday indices (Mon=0..Sun=6) in display order, RTL-friendly
    (right-most column is the first day of the week)."""
    start = WEEKDAY_STARTS.get(week_start, WEEKDAY_STARTS["saturday"])
    return [(start + i) % 7 for i in range(7)]


def _weekday_name(idx: int) -> str:
    # ARABIC_WEEKDAYS is Sun..Sat (index 0=Sunday); Python weekday idx is Mon=0..Sun=6.
    py_to_name = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6}
    return ARABIC_WEEKDAYS[py_to_name[idx]]


def _title_page(page_w: float, page_h: float, title: str, year: int, style: dict) -> SvgPage:
    p = SvgPage(page_w, page_h)
    p.rect(0, 0, page_w, page_h, fill=style["fill"])
    p.rect(page_w * 0.08, page_h * 0.35, page_w * 0.84, page_h * 0.3, fill="none", stroke=style["accent"], stroke_width=2)
    p.text(page_w / 2, page_h * 0.46, title, size=30, weight="bold", font=ARABIC_HEADING_FONT_STACK, fill=style["accent"])
    p.text(page_w / 2, page_h * 0.55, to_arabic_indic_digits(year), size=22, font=ARABIC_HEADING_FONT_STACK, fill=style["accent"])
    return p


def _month_overview_page(page_w: float, page_h: float, year: int, month: int, week_start: str, style: dict) -> SvgPage:
    p = SvgPage(page_w, page_h)
    margin = page_w * 0.06
    p.text(page_w / 2, page_h * 0.1, f"{ARABIC_MONTHS[month - 1]} {to_arabic_indic_digits(year)}",
           size=22, weight="bold", font=ARABIC_HEADING_FONT_STACK, fill=style["accent"])

    grid_top = page_h * 0.16
    grid_bottom = page_h * 0.92
    grid_left = margin
    grid_right = page_w - margin
    cols = 7
    col_w = (grid_right - grid_left) / cols
    order = _ordered_weekdays(week_start)

    header_h = (grid_bottom - grid_top) * 0.08
    for i, wd in enumerate(order):
        cx = grid_right - (i + 0.5) * col_w
        p.text(cx, grid_top + header_h * 0.7, _weekday_name(wd), size=11, weight="bold", fill=style["accent"])

    cal = calendar.Calendar(firstweekday=order[0])
    week_rows = cal.monthdatescalendar(year, month)
    rows = len(week_rows)
    row_h = (grid_bottom - grid_top - header_h) / max(rows, 1)

    p.rect(grid_left, grid_top, grid_right - grid_left, grid_bottom - grid_top, stroke=style["grid"], stroke_width=1)
    p.line(grid_left, grid_top + header_h, grid_right, grid_top + header_h, stroke=style["grid"], stroke_width=1)

    for r, week_row in enumerate(week_rows):
        y0 = grid_top + header_h + r * row_h
        for c, date_obj in enumerate(week_row):
            x0 = grid_right - (c + 1) * col_w
            p.rect(x0, y0, col_w, row_h, stroke=style["grid"], stroke_width=0.6)
            if date_obj.month == month:
                p.text(x0 + col_w - 6, y0 + 14, to_arabic_indic_digits(date_obj.day), size=10, anchor="end", fill="#222")
    return p


def _weekly_page(page_w: float, page_h: float, year: int, month: int, week_dates: list[dt.date], week_start: str, style: dict) -> SvgPage:
    p = SvgPage(page_w, page_h)
    margin = page_w * 0.06
    first, last = week_dates[0], week_dates[-1]
    header = f"أسبوع {to_arabic_indic_digits(first.day)} - {to_arabic_indic_digits(last.day)} {ARABIC_MONTHS[month - 1]}"
    p.text(page_w / 2, page_h * 0.08, header, size=18, weight="bold", font=ARABIC_HEADING_FONT_STACK, fill=style["accent"])

    order = _ordered_weekdays(week_start)
    grid_top = page_h * 0.13
    grid_bottom = page_h * 0.85
    grid_left = margin
    grid_right = page_w - margin
    row_h = (grid_bottom - grid_top) / 7

    for i, (wd, date_obj) in enumerate(zip(order, week_dates)):
        y0 = grid_top + i * row_h
        p.rect(grid_left, y0, grid_right - grid_left, row_h, stroke=style["grid"], stroke_width=0.8)
        p.text(grid_right - 8, y0 + row_h * 0.35, f"{_weekday_name(wd)} {to_arabic_indic_digits(date_obj.day)}",
               size=11, weight="bold", anchor="end", fill=style["accent"])
        for ln in range(2):
            ly = y0 + row_h * (0.55 + ln * 0.35)
            p.line(grid_left + 6, ly, grid_right - 6, ly, stroke=style["grid"], stroke_width=0.5, dasharray="2,3")

    notes_top = grid_bottom + page_h * 0.02
    p.text(grid_right, notes_top, "أولويات الأسبوع", size=12, weight="bold", anchor="end", fill=style["accent"])
    for i in range(3):
        cy = notes_top + 16 + i * 14
        p.circle(grid_right - 6, cy - 3, 3, stroke=style["accent"])
        p.line(grid_left, cy, grid_right - 16, cy, stroke=style["grid"], stroke_width=0.6, dasharray="2,3")
    return p


def _habit_tracker_page(page_w: float, page_h: float, year: int, month: int, style: dict) -> SvgPage:
    p = SvgPage(page_w, page_h)
    p.text(page_w / 2, page_h * 0.08, f"متابعة العادات - {ARABIC_MONTHS[month - 1]}",
           size=18, weight="bold", font=ARABIC_HEADING_FONT_STACK, fill=style["accent"])
    days_in_month = calendar.monthrange(year, month)[1]
    margin = page_w * 0.08
    grid_top = page_h * 0.14
    grid_bottom = page_h * 0.92
    grid_left = margin
    grid_right = page_w - margin
    habit_col_w = (grid_right - grid_left) * 0.22
    day_area_left = grid_left
    day_area_right = grid_right - habit_col_w
    col_w = (day_area_right - day_area_left) / days_in_month
    n_habits = 6
    row_h = (grid_bottom - grid_top) / (n_habits + 1)

    p.text(grid_right - habit_col_w / 2, grid_top + row_h * 0.6, "العادة", size=11, weight="bold", fill=style["accent"])
    for d in range(days_in_month):
        cx = day_area_right - (d + 0.5) * col_w
        p.text(cx, grid_top + row_h * 0.6, to_arabic_indic_digits(d + 1), size=7, fill="#555")

    for h in range(1, n_habits + 1):
        y0 = grid_top + h * row_h
        p.line(grid_left, y0, grid_right, y0, stroke=style["grid"], stroke_width=0.6)
        for d in range(days_in_month):
            cx = day_area_right - (d + 0.5) * col_w
            p.circle(cx, y0 + row_h * 0.5, 3.5, stroke=style["grid"], stroke_width=0.8)
    p.line(day_area_right, grid_top, day_area_right, grid_bottom, stroke=style["grid"], stroke_width=1)
    return p


def generate_planner_pdf(spec: dict, trim_size: str, title: str, out_path: Path) -> int:
    trim_w, trim_h = kdp_specs.get_trim_size(trim_size)
    page_w, page_h = page_size_pt(trim_w, trim_h, bleed_in=kdp_specs.BLEED_IN)
    style = STYLE_ACCENTS.get(spec.get("style", "minimal"), STYLE_ACCENTS["minimal"])

    year = spec["year"]
    start_month = spec.get("start_month", 1)
    end_month = spec.get("end_month", 12)
    week_start = spec.get("week_start", "saturday")
    kind = spec.get("kind", "weekly")
    include_habits = spec.get("include_habit_tracker", False)

    pages = [_title_page(page_w, page_h, title, year, style)]

    for month in range(start_month, end_month + 1):
        pages.append(_month_overview_page(page_w, page_h, year, month, week_start, style))
        if include_habits:
            pages.append(_habit_tracker_page(page_w, page_h, year, month, style))
        if kind == "weekly":
            order = _ordered_weekdays(week_start)
            cal = calendar.Calendar(firstweekday=order[0])
            for week in cal.monthdatescalendar(year, month):
                if all(d.month != month for d in week):
                    continue
                pages.append(_weekly_page(page_w, page_h, year, month, list(week), week_start, style))

    return svg_pages_to_pdf(pages, out_path), len(pages)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a planner low-content interior PDF")
    parser.add_argument("--spec", required=True, help="Path to a YAML file with the spec block")
    parser.add_argument("--trim-size", default="8.5x11")
    parser.add_argument("--title", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    spec = yaml.safe_load(Path(args.spec).read_text(encoding="utf-8"))
    _, n = generate_planner_pdf(spec, args.trim_size, args.title, Path(args.out))
    print(f"Wrote {args.out} ({n} pages)")


if __name__ == "__main__":
    main()
