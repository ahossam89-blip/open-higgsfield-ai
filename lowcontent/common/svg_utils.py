"""Minimal SVG page builder for parametric low-content book generators
(planners, workbooks). Deliberately dependency-light: builds raw SVG XML
strings rather than pulling in a full SVG library, since every page here is
just rects/lines/text/circles.

Coordinate system: points (1in = 72pt), matching PDF units, so trim-size
math from common/kdp_specs.py maps directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.sax.saxutils import escape

PT_PER_IN = 72.0

ARABIC_FONT_STACK = "'Amiri','Cairo','Noto Naskh Arabic',serif"
ARABIC_HEADING_FONT_STACK = "'Cairo','Amiri',sans-serif"


@dataclass
class SvgPage:
    width_pt: float
    height_pt: float
    elements: list[str] = field(default_factory=list)

    def rect(
        self, x: float, y: float, w: float, h: float,
        fill: str = "none", stroke: str = "none", stroke_width: float = 1.0,
        rx: float = 0, dasharray: str | None = None, opacity: float = 1.0,
    ) -> None:
        dash = f' stroke-dasharray="{dasharray}"' if dasharray else ""
        self.elements.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'rx="{rx:.2f}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{stroke_width}" opacity="{opacity}"{dash}/>'
        )

    def line(
        self, x1: float, y1: float, x2: float, y2: float,
        stroke: str = "#000", stroke_width: float = 1.0, dasharray: str | None = None,
        opacity: float = 1.0,
    ) -> None:
        dash = f' stroke-dasharray="{dasharray}"' if dasharray else ""
        self.elements.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}" opacity="{opacity}"{dash}/>'
        )

    def circle(self, cx: float, cy: float, r: float, fill: str = "none", stroke: str = "#000", stroke_width: float = 1.0) -> None:
        self.elements.append(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}"/>'
        )

    def text(
        self, x: float, y: float, content: str, size: float = 12,
        anchor: str = "middle", font: str = ARABIC_FONT_STACK, weight: str = "normal",
        fill: str = "#111", rtl: bool = True, opacity: float = 1.0,
    ) -> None:
        direction = ' direction="rtl"' if rtl else ""
        self.elements.append(
            f'<text x="{x:.2f}" y="{y:.2f}" font-family="{font}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" opacity="{opacity}"{direction}>'
            f"{escape(content)}</text>"
        )

    def group_start(self, transform: str = "") -> None:
        attr = f' transform="{transform}"' if transform else ""
        self.elements.append(f"<g{attr}>")

    def group_end(self) -> None:
        self.elements.append("</g>")

    def raw(self, svg_fragment: str) -> None:
        self.elements.append(svg_fragment)

    def to_svg(self) -> str:
        body = "\n".join(self.elements)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{self.width_pt:.2f}pt" height="{self.height_pt:.2f}pt" '
            f'viewBox="0 0 {self.width_pt:.2f} {self.height_pt:.2f}">\n'
            f'<rect x="0" y="0" width="{self.width_pt:.2f}" height="{self.height_pt:.2f}" fill="#ffffff"/>\n'
            f"{body}\n</svg>"
        )


def page_size_pt(trim_width_in: float, trim_height_in: float, bleed_in: float = 0.0) -> tuple[float, float]:
    return (
        (trim_width_in + 2 * bleed_in) * PT_PER_IN,
        (trim_height_in + 2 * bleed_in) * PT_PER_IN,
    )


def dotted_trace_line(page: SvgPage, x1: float, x2: float, y: float, stroke: str = "#999", stroke_width: float = 1.2) -> None:
    """A single dashed baseline used for handwriting practice."""
    page.line(x1, y, x2, y, stroke=stroke, stroke_width=stroke_width, dasharray="4,4")


def four_line_writing_guide(
    page: SvgPage, x1: float, x2: float, y_top: float, row_height: float,
    solid: str = "#333", dashed: str = "#aaa",
) -> None:
    """Classic Arabic-script practice ruling: top guide, x-height dashed
    midline, baseline (solid), descender guide."""
    page.line(x1, y_top, x2, y_top, stroke=dashed, stroke_width=0.8, dasharray="2,3")
    mid = y_top + row_height * 0.45
    page.line(x1, mid, x2, mid, stroke=dashed, stroke_width=0.8, dasharray="2,3")
    baseline = y_top + row_height * 0.75
    page.line(x1, baseline, x2, baseline, stroke=solid, stroke_width=1.2)
    bottom = y_top + row_height
    page.line(x1, bottom, x2, bottom, stroke=dashed, stroke_width=0.8, dasharray="2,3")


ARABIC_WEEKDAYS = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"]
ARABIC_MONTHS = [
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
]
ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"


def to_arabic_indic_digits(n: int | str) -> str:
    return str(n).translate(str.maketrans("0123456789", ARABIC_INDIC_DIGITS))
