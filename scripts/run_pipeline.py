"""End-to-end orchestrator: pick the next queued book from books.yaml and
run it through the full pipeline:

    queued -> [build interior + covers + ebook + metadata] -> generated
    generated -> [qa/run_qa.py]                              -> qa_passed | failed
    qa_passed -> [packaging/package_book.py]                 -> packaged

("packaged" -> "published" happens in the GitHub Action, after the
packaged deliverables are successfully attached to a release — that step
is CI-environment specific, not part of this script.)

Usage:
    python -m scripts.run_pipeline                # process next queued book
    python -m scripts.run_pipeline --id BOOK_ID    # process a specific book
    python -m scripts.run_pipeline --dry-run       # show what would run
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bilingual.build import build_bilingual
from classics.build import build_classic
from common import kdp_specs
from common.queue import find_book, next_queued_book, update_status
from covers.generate_cover import compute_layout_for_binding, generate_cover_pdf
from ebook.generate_epub import generate_ebook
from lowcontent.planners.generate_planner import generate_planner_pdf
from lowcontent.workbooks.generate_workbook import generate_workbook_pdf
from bookpack.package_book import package_book
from metadata.export_csv import export_csv
from metadata.generate_metadata import generate_metadata
from qa.run_qa import run_qa

OUTPUT_ROOT = REPO_ROOT / "output"


class PipelineError(RuntimeError):
    pass


def _build_interior(book: dict, out_dir: Path) -> tuple[Path, int]:
    if book["type"] == "classic":
        return build_classic(book)

    if book["type"] == "bilingual":
        return build_bilingual(book)

    if book["type"] == "lowcontent":
        generator = book.get("generator")
        spec = book.get("spec", {})
        out_pdf = out_dir / f"{book['id']}-interior.pdf"
        if generator == "planner":
            _, n = generate_planner_pdf(spec, book["trim_size"], book["title_ar"], out_pdf)
        elif generator == "workbook":
            _, n = generate_workbook_pdf(spec, book["trim_size"], book["title_ar"], out_pdf)
        else:
            raise PipelineError(f"Unknown lowcontent generator '{generator}' for book '{book['id']}'")
        return out_pdf, n

    raise PipelineError(f"Unknown book type '{book['type']}' for book '{book['id']}'")


def _build_formats(book: dict, out_dir: Path, page_count: int, metadata: dict) -> dict:
    """Generate the per-format deliverables (print covers, ebook) requested
    in book['formats']. Returns the manifest's "formats" sub-dict."""
    formats: dict = {}
    title = metadata.get("title", book["title_ar"])
    subtitle = metadata.get("subtitle", "")
    blurb = metadata.get("description", "")[:600]
    style = book.get("cover_style", "classic")
    paper_type = book.get("paper_type", "white")

    for fmt in book["formats"]:
        if fmt in ("paperback", "hardcover"):
            layout = compute_layout_for_binding(fmt, book["trim_size"], page_count, paper_type)
            cover_pdf = out_dir / f"{book['id']}-cover-{fmt}.pdf"
            generate_cover_pdf(
                layout=layout,
                title_ar=title,
                author_ar=book.get("author_ar", ""),
                subtitle_ar=subtitle,
                blurb_ar=blurb,
                style=style,
                out_path=cover_pdf,
            )
            formats[fmt] = {
                "cover_pdf": str(cover_pdf.relative_to(REPO_ROOT)),
                "spine_width_in": layout.spine_width_in,
                "sheet_width_in": layout.sheet_width_in,
                "sheet_height_in": layout.sheet_height_in,
            }
        elif fmt == "ebook":
            epub_path = generate_ebook(book, out_dir)
            formats["ebook"] = {"epub": str(epub_path.relative_to(REPO_ROOT))}
        else:
            raise PipelineError(f"Unknown format '{fmt}' for book '{book['id']}'")

    return formats


def process_book(book: dict) -> dict:
    out_dir = OUTPUT_ROOT / book["id"]
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== [{book['id']}] stage: generating ({book['type']}, formats={book['formats']}) ===")
    interior_pdf, page_count = _build_interior(book, out_dir)
    page_count = max(page_count, kdp_specs.MIN_PAGE_COUNT)

    print(f"[metadata] generating listing metadata for '{book['id']}' via Claude API ...")
    metadata = generate_metadata(book, out_dir)

    print(f"[formats] generating {book['formats']} for '{book['id']}' ...")
    formats = _build_formats(book, out_dir, page_count, metadata)

    manifest = {
        "book_id": book["id"],
        "type": book["type"],
        "series": book.get("series"),
        "trim_size": book["trim_size"],
        "paper_type": book.get("paper_type", "white"),
        "page_count": page_count,
        "interior_pdf": str(interior_pdf.relative_to(REPO_ROOT)),
        "formats": formats,
        "metadata_path": str((out_dir / "metadata.json").relative_to(REPO_ROOT)),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    update_status(book["id"], "generated")
    print(f"=== [{book['id']}] generated: {page_count} pages, formats {list(formats)} ===")

    print(f"=== [{book['id']}] stage: QA ===")
    report = run_qa(book)
    for c in report.checks:
        mark = "PASS" if c["passed"] else "FAIL"
        print(f"  [{mark}] {c['name']}" + (f" — {c['detail']}" if c["detail"] else ""))
    if not report.passed:
        update_status(book["id"], "failed", notes=report.summary())
        raise PipelineError(report.summary())
    update_status(book["id"], "qa_passed")
    print(f"=== [{book['id']}] {report.summary()} ===")

    print(f"=== [{book['id']}] stage: packaging ===")
    book_after_qa = find_book(book["id"])
    zip_path = package_book(book_after_qa)
    update_status(book["id"], "packaged")
    manifest["package_zip"] = str(zip_path.relative_to(REPO_ROOT))
    print(f"=== [{book['id']}] packaged: {zip_path} ===")

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the book factory pipeline for one queued book")
    parser.add_argument("--id", help="Process this specific book id instead of the next queued one")
    parser.add_argument("--dry-run", action="store_true", help="Print which book would run and exit")
    args = parser.parse_args()

    book = find_book(args.id) if args.id else next_queued_book()
    if book is None:
        print("No queued books to process." if not args.id else f"Book '{args.id}' not found.")
        return

    if args.dry_run:
        print(f"Would process: {book['id']} ({book['type']}, formats={book['formats']}, trim {book['trim_size']})")
        return

    try:
        manifest = process_book(book)
    except Exception as exc:  # noqa: BLE001 - surface full traceback; status already set by process_book on QA failure
        traceback.print_exc()
        if find_book(book["id"])["status"] != "failed":
            update_status(book["id"], "failed", notes=f"Pipeline error: {exc}")
        raise SystemExit(1) from exc

    export_csv(OUTPUT_ROOT / "upload_checklist.csv")

    # Small breadcrumb for CI: which book this run processed, and where its
    # release assets landed, without having to re-scan books.yaml/output/.
    (OUTPUT_ROOT / "_last_run.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
