"""Typeset a bilingual book's generated content into a print-ready,
KDP-compliant facing-page interior PDF (English on left/verso pages,
Arabic on right/recto pages) using Jinja2 + WeasyPrint.

Facing pairing is enforced with CSS `page-break-before: left|right` per
paragraph pair, not by guessing page counts — WeasyPrint inserts a blank
page automatically whenever one side runs long, so pairs never drift.

Margins use the same two-pass KDP-margin-by-page-count approach as
classics/typeset.py, reusing common/kdp_specs.get_interior_margins.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from pypdf import PdfReader

from common import kdp_specs

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
MAX_PASSES = 3


def _paragraphs(text: str) -> list[str]:
    import re
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def _render_context(book: dict, content: dict) -> dict:
    return {
        "title_ar": book["title_ar"],
        "title_en": book.get("title_en", book["title_ar"]),
        "author_ar": book.get("author_ar", ""),
        "generation_date": dt.date.today().isoformat(),
        "preface_paragraphs": _paragraphs(content["translator_preface_en"]),
        "chapters": content["chapters"],
        "glossary": sorted(content.get("glossary", []), key=lambda g: g.get("term", "")),
    }


def render_pdf(book: dict, content: dict, out_path: Path) -> int:
    trim_w, trim_h = kdp_specs.get_trim_size(book["trim_size"])
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("bilingual_book.html.j2")
    ctx = _render_context(book, content)

    page_count_guess = 300  # bilingual books run long; start the gutter guess higher
    pdf_bytes = None
    for _ in range(MAX_PASSES):
        margins = kdp_specs.get_interior_margins(page_count_guess)
        html_str = template.render(
            **ctx,
            page_width_in=trim_w,
            page_height_in=trim_h,
            margin_top_in=margins.top_in,
            margin_bottom_in=margins.bottom_in,
            margin_inside_in=margins.inside_in,
            margin_outside_in=margins.outside_in,
        )
        pdf_bytes = HTML(string=html_str, base_url=str(TEMPLATE_DIR)).write_pdf()
        actual_pages = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
        if kdp_specs.gutter_for_page_count(actual_pages) == kdp_specs.gutter_for_page_count(page_count_guess):
            page_count_guess = actual_pages
            break
        page_count_guess = actual_pages

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(pdf_bytes)
    return page_count_guess


def typeset_book(book: dict, out_dir: Path) -> tuple[Path, int]:
    content = json.loads((out_dir / "bilingual_content.json").read_text(encoding="utf-8"))
    out_pdf = out_dir / f"{book['id']}-interior.pdf"
    page_count = render_pdf(book, content, out_pdf)
    return out_pdf, page_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Typeset a bilingual book interior PDF")
    parser.add_argument("--dir", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--title-en", default="")
    parser.add_argument("--author", default="")
    parser.add_argument("--trim-size", default="6x9")
    args = parser.parse_args()

    book = {
        "title_ar": args.title,
        "title_en": args.title_en or args.title,
        "author_ar": args.author,
        "trim_size": args.trim_size,
        "id": "cli",
    }
    out_pdf, page_count = typeset_book(book, Path(args.dir))
    print(f"Wrote {out_pdf} ({page_count} pages)")


if __name__ == "__main__":
    main()
