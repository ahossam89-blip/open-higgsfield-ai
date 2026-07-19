"""Compile per-book metadata.json + production artifacts into a single KDP
upload-checklist CSV covering every book in books.yaml.

Run after metadata/generate_metadata.py has produced output/<id>/metadata.json
for the books you want included; books without metadata.json are still
listed with blank metadata columns so the checklist stays a complete queue
view.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from common.queue import load_queue

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = REPO_ROOT / "output"

CSV_COLUMNS = [
    "book_id",
    "type",
    "series",
    "series_line",
    "status",
    "formats",
    "title",
    "subtitle",
    "author",
    "language",
    "trim_size",
    "paper_type",
    "page_count",
    "categories",
    "keyword_1",
    "keyword_2",
    "keyword_3",
    "keyword_4",
    "keyword_5",
    "keyword_6",
    "keyword_7",
    "description",
    "ai_content_disclosure",
    "interior_pdf",
    "cover_pdf_paperback",
    "cover_pdf_hardcover",
    "ebook_epub",
    "package_zip",
    "notes",
]

# KDP requires disclosing AI-generated content in the title's "AI Content"
# section of the Publishing Details form at upload time — this is a
# per-book reminder, not something the pipeline can tick on your behalf.
_AI_DISCLOSURE = {
    "classic": (
        "AI-generated book content: original ~1,500-word introduction, chapter "
        "annotations, and glossary (Claude API). The classical Arabic source text "
        "itself is NOT AI-generated. Disclose under KDP Publishing Details -> AI Content."
    ),
    "bilingual": (
        "AI-generated book content: English translation, translator's preface, "
        "introduction, chapter annotations, and glossary (Claude API). The classical "
        "Arabic source text itself is NOT AI-generated. Disclose under KDP Publishing "
        "Details -> AI Content."
    ),
    "lowcontent": (
        "No AI-generated book content — interior is programmatically generated "
        "(no Claude-authored text). No AI Content disclosure required for the interior. "
        "(Listing metadata — title/subtitle/keywords/description — was AI-assisted; "
        "KDP disclosure applies to book content, not marketing metadata.)"
    ),
}


def _book_row(book: dict) -> dict:
    out_dir = OUTPUT_ROOT / book["id"]
    metadata_path = out_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    keywords = metadata.get("keywords", [])
    keywords = (keywords + [""] * 7)[:7]

    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    formats = manifest.get("formats", {})

    row = {
        "book_id": book["id"],
        "type": book["type"],
        "series": book.get("series", ""),
        "series_line": metadata.get("series_line", ""),
        "status": book["status"],
        "formats": " | ".join(book.get("formats", [])),
        "title": metadata.get("title", book.get("title_ar", "")),
        "subtitle": metadata.get("subtitle", ""),
        "author": book.get("author_ar", ""),
        "language": "Arabic/English" if book["type"] == "bilingual" else "Arabic",
        "trim_size": book["trim_size"],
        "paper_type": book.get("paper_type", "white"),
        "page_count": manifest.get("page_count", ""),
        "categories": " | ".join(metadata.get("categories", [])),
        "description": metadata.get("description", ""),
        "ai_content_disclosure": _AI_DISCLOSURE.get(book["type"], ""),
        "interior_pdf": manifest.get("interior_pdf", ""),
        "cover_pdf_paperback": formats.get("paperback", {}).get("cover_pdf", ""),
        "cover_pdf_hardcover": formats.get("hardcover", {}).get("cover_pdf", ""),
        "ebook_epub": formats.get("ebook", {}).get("epub", ""),
        "package_zip": manifest.get("package_zip", ""),
        "notes": book.get("notes", ""),
    }
    for i, kw in enumerate(keywords, start=1):
        row[f"keyword_{i}"] = kw
    return row


def export_csv(out_path: Path) -> Path:
    books = load_queue()
    rows = [_book_row(b) for b in books]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the KDP upload-checklist CSV")
    parser.add_argument("--out", default=str(OUTPUT_ROOT / "upload_checklist.csv"))
    args = parser.parse_args()

    dest = export_csv(Path(args.out))
    print(f"Wrote {dest}")


if __name__ == "__main__":
    main()
