"""Orchestrate the full classics pipeline for one book entry:
ingest -> clean -> generate (Claude) -> typeset -> interior PDF.

Writes all intermediate artifacts to output/<book_id>/ and returns the
final interior PDF path + resulting page count (needed by covers/).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from classics.clean import clean_book
from classics.generate import generate_book_content
from classics.ingest import ingest_book
from classics.typeset import typeset_book
from common.queue import find_book

OUTPUT_ROOT = REPO_ROOT / "output"


def build_classic(book: dict) -> tuple[Path, int]:
    out_dir = OUTPUT_ROOT / book["id"]
    print(f"[classics] ingesting {book['id']} ...")
    ingest_book(book, out_dir)

    print(f"[classics] cleaning {book['id']} ...")
    clean_book(book, out_dir)

    print(f"[classics] generating editorial content for {book['id']} via Claude API ...")
    generate_book_content(book, out_dir)

    print(f"[classics] typesetting {book['id']} ...")
    interior_pdf, page_count = typeset_book(book, out_dir)
    print(f"[classics] done: {interior_pdf} ({page_count} pages)")
    return interior_pdf, page_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a classic book end-to-end")
    parser.add_argument("--id", required=True, help="Book id from books.yaml")
    args = parser.parse_args()

    book = find_book(args.id)
    if book is None:
        raise SystemExit(f"Book '{args.id}' not found in books.yaml")
    if book["type"] != "classic":
        raise SystemExit(f"Book '{args.id}' is not type=classic")

    build_classic(book)


if __name__ == "__main__":
    main()
