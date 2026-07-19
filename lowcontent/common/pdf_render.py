"""Render a sequence of SVG pages (see svg_utils.SvgPage) into a single
merged, print-ready PDF."""

from __future__ import annotations

import io
from pathlib import Path

import cairosvg
from pypdf import PdfReader, PdfWriter

from lowcontent.common.svg_utils import SvgPage


def svg_pages_to_pdf(pages: list[SvgPage], out_path: Path) -> Path:
    writer = PdfWriter()
    for page in pages:
        svg_bytes = page.to_svg().encode("utf-8")
        page_pdf_bytes = cairosvg.svg2pdf(bytestring=svg_bytes)
        reader = PdfReader(io.BytesIO(page_pdf_bytes))
        for p in reader.pages:
            writer.add_page(p)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as fh:
        writer.write(fh)
    return out_path


def page_count(pdf_path: Path) -> int:
    return len(PdfReader(str(pdf_path)).pages)
