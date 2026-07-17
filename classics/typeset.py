"""Typeset a classic book's generated content into a print-ready,
KDP-compliant interior PDF using an Arabic RTL Jinja2 + WeasyPrint template.

Margins depend on final page count (KDP's gutter table), which depends on
the render itself, so this does a two-pass render: an initial pass with a
reasonable default gutter, a page count, then a final pass with the correct
KDP margins for that count (re-rendering again if the tier changed).
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from pypdf import PdfReader

from common import kdp_specs

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
MAX_PASSES = 3


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def _render_context(book: dict, content: dict) -> dict:
    chapters = []
    for ch in content["chapters"]:
        chapters.append(
            {
                "heading": ch["heading"],
                "body_paragraphs": _paragraphs(ch["body"]),
                "annotations": ch.get("annotations", []),
            }
        )
    return {
        "title_ar": book["title_ar"],
        "author_ar": book.get("author_ar", ""),
        "generation_date": dt.date.today().isoformat(),
        "introduction_paragraphs": _paragraphs(content["introduction"]),
        "chapters": chapters,
        "glossary": sorted(content["glossary"], key=lambda g: g.get("term", "")),
    }


def render_pdf(book: dict, content: dict, out_path: Path) -> int:
    trim_w, trim_h = kdp_specs.get_trim_size(book["trim_size"])
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("book.html.j2")
    ctx = _render_context(book, content)

    # Pass 1: render with a mid-tier gutter guess to get a page count.
    page_count_guess = 200
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
    content = json.loads((out_dir / "generated_content.json").read_text(encoding="utf-8"))
    out_pdf = out_dir / f"{book['id']}-interior.pdf"
    page_count = render_pdf(book, content, out_pdf)
    return out_pdf, page_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Typeset a classic book interior PDF")
    parser.add_argument("--dir", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", default="")
    parser.add_argument("--trim-size", default="6x9")
    args = parser.parse_args()

    book = {"title_ar": args.title, "author_ar": args.author, "trim_size": args.trim_size, "id": "cli"}
    out_pdf, page_count = typeset_book(book, Path(args.dir))
    print(f"Wrote {out_pdf} ({page_count} pages)")


if __name__ == "__main__":
    main()
