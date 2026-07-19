"""Orchestrate the full bilingual pipeline for one book entry:
ingest -> clean -> generate (Arabic intro/annotations/glossary, reusing
classics/generate.py) -> translate (English side) -> typeset (facing-page
interior PDF).

Writes all intermediate artifacts to output/<book_id>/, same as classics/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bilingual.translate import translate_book
from bilingual.typeset import typeset_book
from classics.clean import clean_book
from classics.generate import generate_book_content
from classics.ingest import ingest_book
from common.queue import find_book

OUTPUT_ROOT = REPO_ROOT / "output"


def build_bilingual(book: dict) -> tuple[Path, int]:
    out_dir = OUTPUT_ROOT / book["id"]
    print(f"[bilingual] ingesting {book['id']} ...")
    ingest_book(book, out_dir)

    print(f"[bilingual] cleaning {book['id']} ...")
    clean_book(book, out_dir)

    print(f"[bilingual] generating Arabic editorial content for {book['id']} via Claude API ...")
    generate_book_content(book, out_dir)

    print(f"[bilingual] translating {book['id']} to English via Claude API ...")
    translate_book(book, out_dir)

    print(f"[bilingual] typesetting facing-page interior for {book['id']} ...")
    interior_pdf, page_count = typeset_book(book, out_dir)
    print(f"[bilingual] done: {interior_pdf} ({page_count} pages)")
    return interior_pdf, page_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a bilingual book end-to-end")
    parser.add_argument("--id", required=True, help="Book id from books.yaml")
    args = parser.parse_args()

    book = find_book(args.id)
    if book is None:
        raise SystemExit(f"Book '{args.id}' not found in books.yaml")
    if book["type"] != "bilingual":
        raise SystemExit(f"Book '{args.id}' is not type=bilingual")

    build_bilingual(book)


if __name__ == "__main__":
    main()
