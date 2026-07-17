"""End-to-end orchestrator: pick the next queued book from books.yaml,
run its production pipeline (classic or low-content), generate its cover
and KDP metadata, write a manifest, and flip its status.

Used by .github/workflows/weekly-book-factory.yml, and runnable locally:

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

from classics.build import build_classic
from common import kdp_specs
from common.queue import find_book, next_queued_book, update_status
from covers.generate_cover import generate_cover_pdf
from lowcontent.planners.generate_planner import generate_planner_pdf
from lowcontent.workbooks.generate_workbook import generate_workbook_pdf
from metadata.export_csv import export_csv
from metadata.generate_metadata import generate_metadata

OUTPUT_ROOT = REPO_ROOT / "output"


class PipelineError(RuntimeError):
    pass


def _build_interior(book: dict, out_dir: Path) -> tuple[Path, int]:
    if book["type"] == "classic":
        return build_classic(book)

    if book["type"] == "low-content":
        generator = book.get("generator")
        spec = book.get("spec", {})
        out_pdf = out_dir / f"{book['id']}-interior.pdf"
        if generator == "planner":
            _, n = generate_planner_pdf(spec, book["trim_size"], book["title_ar"], out_pdf)
        elif generator == "workbook":
            _, n = generate_workbook_pdf(spec, book["trim_size"], book["title_ar"], out_pdf)
        else:
            raise PipelineError(f"Unknown low-content generator '{generator}' for book '{book['id']}'")
        return out_pdf, n

    raise PipelineError(f"Unknown book type '{book['type']}' for book '{book['id']}'")


def process_book(book: dict) -> dict:
    out_dir = OUTPUT_ROOT / book["id"]
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Processing '{book['id']}' ({book['type']}) ===")
    interior_pdf, page_count = _build_interior(book, out_dir)
    page_count = max(page_count, kdp_specs.MIN_PAGE_COUNT)

    print(f"[metadata] generating listing metadata for '{book['id']}' via Claude API ...")
    metadata = generate_metadata(book, out_dir)

    print(f"[cover] generating full-wrap cover for '{book['id']}' ...")
    layout = kdp_specs.compute_cover_layout(book["trim_size"], page_count, book.get("paper_type", "white"))
    cover_pdf = out_dir / f"{book['id']}-cover.pdf"
    generate_cover_pdf(
        layout=layout,
        title_ar=metadata.get("title", book["title_ar"]),
        author_ar=book.get("author_ar", ""),
        subtitle_ar=metadata.get("subtitle", ""),
        blurb_ar=metadata.get("description", "")[:600],
        style=book.get("cover_style", "classic"),
        out_path=cover_pdf,
    )

    manifest = {
        "book_id": book["id"],
        "type": book["type"],
        "trim_size": book["trim_size"],
        "paper_type": book.get("paper_type", "white"),
        "page_count": page_count,
        "spine_width_in": layout.spine_width_in,
        "interior_pdf": str(interior_pdf.relative_to(REPO_ROOT)),
        "cover_pdf": str(cover_pdf.relative_to(REPO_ROOT)),
        "metadata_path": str((out_dir / "metadata.json").relative_to(REPO_ROOT)),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"=== Finished '{book['id']}': {page_count} pages ===")
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
        print(f"Would process: {book['id']} ({book['type']}, trim {book['trim_size']})")
        return

    update_status(book["id"], "in_progress")
    try:
        manifest = process_book(book)
    except Exception as exc:  # noqa: BLE001 - surface full traceback, then mark failed
        traceback.print_exc()
        update_status(book["id"], "failed", notes=f"Pipeline error: {exc}")
        raise SystemExit(1) from exc

    update_status(book["id"], "published")
    export_csv(OUTPUT_ROOT / "upload_checklist.csv")

    # Small breadcrumb for CI: which book this run processed, and where its
    # release assets landed, without having to re-scan books.yaml/output/.
    (OUTPUT_ROOT / "_last_run.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
