"""Parametric generator for Arabic handwriting / letter-tracing practice
workbooks, driven by the `spec` block of a books.yaml entry.

spec fields:
    kind:                  "letter-tracing" (currently the only kind)
    letters:               "alphabet" or an explicit list of letters
    lines_per_letter:      int, rows of practice per letter page (default 6)
    include_word_practice: bool, append a simple-word tracing section
    difficulty:            "beginner" | "intermediate" (controls row count/spacing)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from common import kdp_specs
from lowcontent.common.pdf_render import svg_pages_to_pdf
from lowcontent.common.svg_utils import (
    ARABIC_HEADING_FONT_STACK,
    SvgPage,
    four_line_writing_guide,
    page_size_pt,
)

# Isolated forms of the 28 Arabic alphabet letters, in dictionary order,
# with their name for the page header.
ARABIC_ALPHABET: list[tuple[str, str]] = [
    ("ا", "ألف"), ("ب", "باء"), ("ت", "تاء"), ("ث", "ثاء"), ("ج", "جيم"),
    ("ح", "حاء"), ("خ", "خاء"), ("د", "دال"), ("ذ", "ذال"), ("ر", "راء"),
    ("ز", "زاي"), ("س", "سين"), ("ش", "شين"), ("ص", "صاد"), ("ض", "ضاد"),
    ("ط", "طاء"), ("ظ", "ظاء"), ("ع", "عين"), ("غ", "غين"), ("ف", "فاء"),
    ("ق", "قاف"), ("ك", "كاف"), ("ل", "لام"), ("م", "ميم"), ("ن", "نون"),
    ("ه", "هاء"), ("و", "واو"), ("ي", "ياء"),
]

SIMPLE_WORDS = [
    "بيت", "قلم", "كتاب", "شمس", "قمر", "ماء", "باب", "ولد",
    "بنت", "سيارة", "شجرة", "طائر", "زهرة", "نهر", "جبل", "بحر",
]

ACCENT = "#173a5e"
GRID_LIGHT = "#cfd8e3"


def _title_page(page_w: float, page_h: float, title: str, style: dict) -> SvgPage:
    p = SvgPage(page_w, page_h)
    p.rect(0, 0, page_w, page_h, fill="#f7f9fc")
    p.rect(page_w * 0.1, page_h * 0.3, page_w * 0.8, page_h * 0.35, fill="none", stroke=ACCENT, stroke_width=2.5)
    p.text(page_w / 2, page_h * 0.42, title, size=26, weight="bold", font=ARABIC_HEADING_FONT_STACK, fill=ACCENT)
    p.text(page_w / 2, page_h * 0.52, "دفتر تمارين الخط العربي", size=15, font=ARABIC_HEADING_FONT_STACK, fill=ACCENT)
    return p


def _letter_page(page_w: float, page_h: float, letter: str, name: str, lines_per_letter: int, difficulty: str) -> SvgPage:
    p = SvgPage(page_w, page_h)
    margin = page_w * 0.08
    p.text(page_w / 2, page_h * 0.08, f"حرف {name}", size=20, weight="bold", font=ARABIC_HEADING_FONT_STACK, fill=ACCENT)

    demo_y = page_h * 0.1
    demo_h = page_h * 0.14
    p.rect(margin, demo_y, page_w - 2 * margin, demo_h, fill="#eef2f8", stroke=GRID_LIGHT, stroke_width=1, rx=6)
    p.text(page_w / 2, demo_y + demo_h * 0.72, letter, size=demo_h * 0.72, weight="bold", fill=ACCENT)

    rows_top = demo_y + demo_h + page_h * 0.03
    rows_bottom = page_h * 0.94
    row_h = (rows_bottom - rows_top) / lines_per_letter
    trace_repeats = 10 if difficulty == "beginner" else 6

    for row in range(lines_per_letter):
        y_top = rows_top + row * row_h
        four_line_writing_guide(p, margin, page_w - margin, y_top, row_h * 0.82)
        baseline = y_top + row_h * 0.82 * 0.75
        # First 2/3 of rows carry faded reference letters to trace; the
        # remainder are blank guide lines for free practice.
        if row < (lines_per_letter * 2) // 3:
            span = (page_w - 2 * margin)
            for i in range(trace_repeats):
                cx = (page_w - margin) - span * (i + 0.5) / trace_repeats
                p.text(cx, baseline, letter, size=row_h * 0.5, fill="#9fb3cc", opacity=0.9)
    return p


def _word_practice_page(page_w: float, page_h: float, words: list[str]) -> SvgPage:
    p = SvgPage(page_w, page_h)
    margin = page_w * 0.08
    p.text(page_w / 2, page_h * 0.08, "تدرّب على كتابة الكلمات", size=20, weight="bold", font=ARABIC_HEADING_FONT_STACK, fill=ACCENT)

    rows_top = page_h * 0.14
    rows_bottom = page_h * 0.94
    row_h = (rows_bottom - rows_top) / len(words)

    for i, word in enumerate(words):
        y_top = rows_top + i * row_h
        label_w = (page_w - 2 * margin) * 0.18
        p.rect(page_w - margin - label_w, y_top, label_w, row_h * 0.7, fill="#eef2f8", stroke=GRID_LIGHT, rx=4)
        p.text(page_w - margin - label_w / 2, y_top + row_h * 0.5, word, size=row_h * 0.32, weight="bold", fill=ACCENT)
        four_line_writing_guide(p, margin, page_w - margin - label_w - 10, y_top, row_h * 0.7)
    return p


def generate_workbook_pdf(spec: dict, trim_size: str, title: str, out_path: Path) -> tuple[Path, int]:
    trim_w, trim_h = kdp_specs.get_trim_size(trim_size)
    page_w, page_h = page_size_pt(trim_w, trim_h, bleed_in=kdp_specs.BLEED_IN)

    letters_cfg = spec.get("letters", "alphabet")
    letters = ARABIC_ALPHABET if letters_cfg == "alphabet" else [(l, l) for l in letters_cfg]
    lines_per_letter = spec.get("lines_per_letter", 6)
    difficulty = spec.get("difficulty", "beginner")
    include_words = spec.get("include_word_practice", True)

    pages = [_title_page(page_w, page_h, title, {})]
    for letter, name in letters:
        pages.append(_letter_page(page_w, page_h, letter, name, lines_per_letter, difficulty))

    if include_words:
        chunk = 8
        for i in range(0, len(SIMPLE_WORDS), chunk):
            pages.append(_word_practice_page(page_w, page_h, SIMPLE_WORDS[i:i + chunk]))

    svg_pages_to_pdf(pages, out_path)
    return out_path, len(pages)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an Arabic handwriting workbook interior PDF")
    parser.add_argument("--spec", required=True, help="Path to a YAML file with the spec block")
    parser.add_argument("--trim-size", default="8.5x11")
    parser.add_argument("--title", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    spec = yaml.safe_load(Path(args.spec).read_text(encoding="utf-8"))
    _, n = generate_workbook_pdf(spec, args.trim_size, args.title, Path(args.out))
    print(f"Wrote {args.out} ({n} pages)")


if __name__ == "__main__":
    main()
