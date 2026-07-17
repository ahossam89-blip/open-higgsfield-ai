"""Automated QA gate: run structural and content sanity checks on a book's
generated artifacts before it's allowed to advance from status "generated"
to "qa_passed".

This is not a substitute for a human proof pass before publishing — it
catches pipeline failures (truncated content, wrong page geometry, empty
sections, mismatched spine width) that would otherwise only surface after
upload to KDP.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

from common import kdp_specs
from common.arabic_text import word_count
from common.queue import find_book

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = REPO_ROOT / "output"

PT_PER_IN = 72.0
SIZE_TOLERANCE_PT = 1.0  # PDF page-box rounding tolerance

INTRO_WORD_RANGE = (1300, 2200)
PREFACE_WORD_RANGE = (700, 1400)
MIN_GLOSSARY_TERMS = 10


@dataclass
class QAReport:
    checks: list[dict] = field(default_factory=list)

    def check(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "passed": bool(passed), "detail": detail})

    @property
    def passed(self) -> bool:
        return all(c["passed"] for c in self.checks)

    def summary(self) -> str:
        failed = [c for c in self.checks if not c["passed"]]
        if not failed:
            return f"QA passed ({len(self.checks)} checks)"
        return "QA FAILED: " + "; ".join(f"{c['name']}: {c['detail']}" for c in failed)


def _pdf_page_count(path: Path) -> int:
    return len(PdfReader(str(path)).pages)


def _pdf_page_size_in(path: Path) -> tuple[float, float]:
    box = PdfReader(str(path)).pages[0].mediabox
    return float(box.width) / PT_PER_IN, float(box.height) / PT_PER_IN


def _check_pdf_exists_and_sized(
    report: QAReport, label: str, path: Path, expected_w_in: float, expected_h_in: float
) -> int | None:
    if not path.exists():
        report.check(f"{label} exists", False, f"missing file: {path}")
        return None
    report.check(f"{label} exists", True)

    try:
        pages = _pdf_page_count(path)
    except Exception as exc:  # noqa: BLE001
        report.check(f"{label} opens", False, f"could not read PDF: {exc}")
        return None
    report.check(f"{label} opens", pages > 0, f"{pages} pages")

    try:
        w_in, h_in = _pdf_page_size_in(path)
    except Exception as exc:  # noqa: BLE001
        report.check(f"{label} page size", False, f"could not read page box: {exc}")
        return pages
    ok = (
        abs(w_in * PT_PER_IN - expected_w_in * PT_PER_IN) <= SIZE_TOLERANCE_PT
        and abs(h_in * PT_PER_IN - expected_h_in * PT_PER_IN) <= SIZE_TOLERANCE_PT
    )
    report.check(
        f"{label} page size",
        ok,
        f"got {w_in:.3f}x{h_in:.3f}in, expected {expected_w_in:.3f}x{expected_h_in:.3f}in",
    )
    return pages


def _check_interior_content(report: QAReport, book: dict, out_dir: Path) -> None:
    if book["type"] == "classic":
        path = out_dir / "generated_content.json"
        if not path.exists():
            report.check("editorial content present", False, "generated_content.json missing")
            return
        content = json.loads(path.read_text(encoding="utf-8"))
        wc = word_count(content.get("introduction", ""))
        lo, hi = INTRO_WORD_RANGE
        report.check("introduction length", lo <= wc <= hi, f"{wc} words (expected {lo}-{hi})")
        glossary = content.get("glossary", [])
        report.check(
            "glossary size", len(glossary) >= MIN_GLOSSARY_TERMS,
            f"{len(glossary)} terms (expected >= {MIN_GLOSSARY_TERMS})",
        )
        chapters = content.get("chapters", [])
        report.check("chapters present", len(chapters) >= 1, f"{len(chapters)} chapters")
        annotated = sum(1 for c in chapters if c.get("annotations"))
        report.check(
            "chapter annotations present", annotated >= 1,
            f"{annotated}/{len(chapters)} chapters have annotations",
        )

    elif book["type"] == "bilingual":
        path = out_dir / "bilingual_content.json"
        if not path.exists():
            report.check("bilingual content present", False, "bilingual_content.json missing")
            return
        content = json.loads(path.read_text(encoding="utf-8"))
        wc = word_count(content.get("translator_preface_en", ""))
        lo, hi = PREFACE_WORD_RANGE
        report.check("translator preface length", lo <= wc <= hi, f"{wc} words (expected {lo}-{hi})")
        chapters = content.get("chapters", [])
        report.check("chapters present", len(chapters) >= 1, f"{len(chapters)} chapters")
        mismatched = [
            c["heading"] for c in chapters
            if len(c.get("paragraphs_ar", [])) != len(c.get("paragraphs_en", []))
        ]
        report.check(
            "paragraph alignment", not mismatched,
            f"paragraph count mismatch in: {mismatched}" if mismatched else "",
        )


def run_qa(book: dict) -> QAReport:
    report = QAReport()
    out_dir = OUTPUT_ROOT / book["id"]
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        report.check("manifest present", False, "manifest.json missing — run the pipeline first")
        return report
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    trim_w, trim_h = kdp_specs.get_trim_size(book["trim_size"])

    if book["type"] in ("classic", "bilingual"):
        interior_path = REPO_ROOT / manifest["interior_pdf"]
        pages = _check_pdf_exists_and_sized(report, "interior", interior_path, trim_w, trim_h)
    elif book["type"] == "lowcontent":
        bleed_trim_w = trim_w + 2 * kdp_specs.BLEED_IN
        bleed_trim_h = trim_h + 2 * kdp_specs.BLEED_IN
        interior_path = REPO_ROOT / manifest["interior_pdf"]
        pages = _check_pdf_exists_and_sized(report, "interior", interior_path, bleed_trim_w, bleed_trim_h)
    else:
        pages = None

    if pages is not None:
        report.check(
            "page count within KDP limits",
            kdp_specs.MIN_PAGE_COUNT <= pages <= kdp_specs.MAX_PAGE_COUNT_BW,
            f"{pages} pages",
        )

    _check_interior_content(report, book, out_dir)

    for fmt, fmt_info in manifest.get("formats", {}).items():
        if fmt in ("paperback", "hardcover"):
            cover_path = REPO_ROOT / fmt_info["cover_pdf"]
            if fmt == "hardcover":
                layout = kdp_specs.compute_hardcover_cover_layout(
                    book["trim_size"], manifest["page_count"], book.get("paper_type", "white")
                )
            else:
                layout = kdp_specs.compute_cover_layout(
                    book["trim_size"], manifest["page_count"], book.get("paper_type", "white")
                )
            _check_pdf_exists_and_sized(
                report, f"{fmt} cover", cover_path, layout.sheet_width_in, layout.sheet_height_in
            )
            recomputed_spine = round(layout.spine_width_in, 4)
            recorded_spine = round(fmt_info.get("spine_width_in", -1), 4)
            report.check(
                f"{fmt} spine width matches page count",
                abs(recomputed_spine - recorded_spine) < 0.001,
                f"recorded {recorded_spine}in, recomputed {recomputed_spine}in",
            )
        elif fmt == "ebook":
            epub_path = REPO_ROOT / fmt_info["epub"]
            if not epub_path.exists():
                report.check("ebook exists", False, f"missing file: {epub_path}")
            else:
                report.check("ebook exists", True)
                try:
                    from ebooklib import epub as epub_lib
                    epub_lib.read_epub(str(epub_path))
                    report.check("ebook opens", True)
                except Exception as exc:  # noqa: BLE001
                    report.check("ebook opens", False, str(exc))

    metadata_path = REPO_ROOT / manifest.get("metadata_path", "")
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        keywords = metadata.get("keywords", [])
        report.check("exactly 7 keywords", len(keywords) == 7, f"{len(keywords)} keywords")
        report.check("description present", bool(metadata.get("description", "").strip()), "")
    else:
        report.check("metadata present", False, f"missing file: {metadata_path}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the QA gate for a book")
    parser.add_argument("--id", required=True)
    args = parser.parse_args()

    book = find_book(args.id)
    if book is None:
        raise SystemExit(f"Book '{args.id}' not found in books.yaml")

    report = run_qa(book)
    for c in report.checks:
        mark = "PASS" if c["passed"] else "FAIL"
        print(f"[{mark}] {c['name']}" + (f" — {c['detail']}" if c["detail"] else ""))
    print(report.summary())
    if not report.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
