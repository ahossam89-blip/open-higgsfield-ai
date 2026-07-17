"""
KDP (Kindle Direct Publishing) paperback interior/cover sizing rules.

All formulas below are transcribed from Amazon KDP's published paperback
specifications (trim sizes, margin/gutter tables, spine-width-per-page-count
constants). Everything is expressed in inches; convert to points/mm at the
call site (see `IN_TO_PT`, `IN_TO_MM`).

References (as published by KDP, subject to Amazon changing them — re-check
before a real print run):
  - Trim sizes: KDP "Choose a trim size" help page.
  - Margins & gutter: KDP "Understanding margins, bleed, and trim" help page.
  - Spine width: KDP "Cover calculator" / spine width formulas.
"""

from __future__ import annotations

from dataclasses import dataclass

IN_TO_PT = 72.0
IN_TO_MM = 25.4
IN_TO_PX_96 = 96.0

BLEED_IN = 0.125          # standard KDP bleed allowance per edge
COVER_SAFETY_MARGIN_IN = 0.25  # keep live text this far from trim edge on covers

# ---------------------------------------------------------------------------
# Trim sizes (width_in, height_in) — the KDP paperback catalogue.
# ---------------------------------------------------------------------------
TRIM_SIZES: dict[str, tuple[float, float]] = {
    "5x8": (5.0, 8.0),
    "5.06x7.81": (5.06, 7.81),
    "5.25x8": (5.25, 8.0),
    "5.5x8.5": (5.5, 8.5),
    "6x9": (6.0, 9.0),
    "6.14x9.21": (6.14, 9.21),
    "6.69x9.61": (6.69, 9.61),
    "7x10": (7.0, 10.0),
    "7.44x9.69": (7.44, 9.69),
    "7.5x9.25": (7.5, 9.25),
    "8x10": (8.0, 10.0),
    "8.25x6": (8.25, 6.0),
    "8.25x8.25": (8.25, 8.25),
    "8.5x8.5": (8.5, 8.5),
    "8.5x11": (8.5, 11.0),
    "a4": (8.27, 11.69),
}

# ---------------------------------------------------------------------------
# Spine width: page_count * factor_per_page (inches), by paper stock.
# ---------------------------------------------------------------------------
SPINE_FACTOR_IN_PER_PAGE: dict[str, float] = {
    "white": 0.002252,
    "cream": 0.0025,
    "color": 0.002347,
}

MIN_PAGES_WITH_SPINE_TEXT = 100  # KDP: spine text only allowed >= 100 pages
MIN_PAGE_COUNT = 24
MAX_PAGE_COUNT_BW = 828
MAX_PAGE_COUNT_COLOR = 590

# ---------------------------------------------------------------------------
# Gutter (inside margin) by page count — KDP no-bleed interior margin table.
# ---------------------------------------------------------------------------
_GUTTER_TABLE: list[tuple[int, int, float]] = [
    (24, 150, 0.375),
    (151, 300, 0.5),
    (301, 500, 0.625),
    (501, 700, 0.75),
    (701, 828, 0.875),
]


def gutter_for_page_count(page_count: int) -> float:
    """Inside (binding-side) margin required by KDP for a given page count."""
    for lo, hi, gutter in _GUTTER_TABLE:
        if lo <= page_count <= hi:
            return gutter
    if page_count < MIN_PAGE_COUNT:
        return _GUTTER_TABLE[0][2]
    return _GUTTER_TABLE[-1][2]


def get_trim_size(name: str) -> tuple[float, float]:
    key = name.strip().lower()
    if key not in TRIM_SIZES:
        raise ValueError(
            f"Unknown trim size '{name}'. Known sizes: {', '.join(sorted(TRIM_SIZES))}"
        )
    return TRIM_SIZES[key]


@dataclass(frozen=True)
class InteriorMargins:
    top_in: float
    bottom_in: float
    inside_in: float   # gutter / binding edge
    outside_in: float  # outer edge


def get_interior_margins(
    page_count: int,
    top_in: float = 0.5,
    bottom_in: float = 0.5,
    outside_in: float = 0.5,
) -> InteriorMargins:
    """
    KDP hard minimums are top/bottom/outside >= 0.25in and inside >= the
    gutter table value. We default to a more readable 0.5in on the
    non-gutter edges (typography convention for print books) but callers
    may tighten toward the 0.25in KDP floor if they need more text area.
    """
    for name, val in (("top_in", top_in), ("bottom_in", bottom_in), ("outside_in", outside_in)):
        if val < 0.25:
            raise ValueError(f"{name}={val} is below the KDP minimum of 0.25in")
    return InteriorMargins(
        top_in=top_in,
        bottom_in=bottom_in,
        inside_in=gutter_for_page_count(page_count),
        outside_in=outside_in,
    )


def spine_width_in(page_count: int, paper_type: str = "white") -> float:
    if paper_type not in SPINE_FACTOR_IN_PER_PAGE:
        raise ValueError(
            f"Unknown paper_type '{paper_type}'. Use one of {list(SPINE_FACTOR_IN_PER_PAGE)}"
        )
    if page_count < MIN_PAGE_COUNT:
        raise ValueError(f"page_count={page_count} is below KDP minimum of {MIN_PAGE_COUNT}")
    return round(page_count * SPINE_FACTOR_IN_PER_PAGE[paper_type], 4)


def spine_text_allowed(page_count: int) -> bool:
    return page_count >= MIN_PAGES_WITH_SPINE_TEXT


@dataclass(frozen=True)
class CoverLayout:
    """Full wraparound cover geometry in inches, origin at bottom-left of the
    bleed sheet (back cover on the left, spine center, front cover on the
    right — matches how the sheet reads before being wrapped)."""
    trim_width_in: float
    trim_height_in: float
    page_count: int
    paper_type: str
    spine_width_in: float
    bleed_in: float
    sheet_width_in: float
    sheet_height_in: float
    back_x0_in: float
    back_x1_in: float
    spine_x0_in: float
    spine_x1_in: float
    front_x0_in: float
    front_x1_in: float
    safety_margin_in: float


def compute_cover_layout(
    trim_size: str,
    page_count: int,
    paper_type: str = "white",
    bleed_in: float = BLEED_IN,
) -> CoverLayout:
    trim_w, trim_h = get_trim_size(trim_size)
    spine_w = spine_width_in(page_count, paper_type)

    sheet_width = bleed_in + trim_w + spine_w + trim_w + bleed_in
    sheet_height = trim_h + 2 * bleed_in

    back_x0 = 0.0
    back_x1 = bleed_in + trim_w
    spine_x0 = back_x1
    spine_x1 = spine_x0 + spine_w
    front_x0 = spine_x1
    front_x1 = sheet_width

    return CoverLayout(
        trim_width_in=trim_w,
        trim_height_in=trim_h,
        page_count=page_count,
        paper_type=paper_type,
        spine_width_in=spine_w,
        bleed_in=bleed_in,
        sheet_width_in=round(sheet_width, 4),
        sheet_height_in=round(sheet_height, 4),
        back_x0_in=round(back_x0, 4),
        back_x1_in=round(back_x1, 4),
        spine_x0_in=round(spine_x0, 4),
        spine_x1_in=round(spine_x1, 4),
        front_x0_in=round(front_x0, 4),
        front_x1_in=round(front_x1, 4),
        safety_margin_in=COVER_SAFETY_MARGIN_IN,
    )


def clamp_page_count_for_color(page_count: int, paper_type: str) -> int:
    cap = MAX_PAGE_COUNT_COLOR if paper_type == "color" else MAX_PAGE_COUNT_BW
    return min(page_count, cap)
