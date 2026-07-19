"""Assemble a QA-passed book's final per-format deliverables into
output/<id>/package/ — the exact set of files to upload to KDP for each
format — and zip them for convenient download from the GitHub release.

Only runs after status == "qa_passed" (enforced by scripts/run_pipeline.py).
"""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path

from common.queue import find_book

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = REPO_ROOT / "output"


def package_book(book: dict) -> Path:
    out_dir = OUTPUT_ROOT / book["id"]
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    package_dir = out_dir / "package"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True)

    copied: dict[str, str] = {}

    if "interior_pdf" in manifest:
        src = REPO_ROOT / manifest["interior_pdf"]
        dest = package_dir / f"{book['id']}-interior.pdf"
        shutil.copy2(src, dest)
        copied["interior_pdf"] = dest.name

    for fmt, fmt_info in manifest.get("formats", {}).items():
        if fmt in ("paperback", "hardcover"):
            src = REPO_ROOT / fmt_info["cover_pdf"]
            dest = package_dir / f"{book['id']}-cover-{fmt}.pdf"
            shutil.copy2(src, dest)
            copied[f"{fmt}_cover"] = dest.name
        elif fmt == "ebook":
            src = REPO_ROOT / fmt_info["epub"]
            dest = package_dir / f"{book['id']}.epub"
            shutil.copy2(src, dest)
            copied["ebook"] = dest.name

    metadata_src = REPO_ROOT / manifest["metadata_path"]
    metadata_dest = package_dir / "metadata.json"
    shutil.copy2(metadata_src, metadata_dest)
    copied["metadata"] = metadata_dest.name

    package_manifest = {
        "book_id": book["id"],
        "title_ar": book["title_ar"],
        "series": book.get("series"),
        "formats": book["formats"],
        "page_count": manifest.get("page_count"),
        "files": copied,
    }
    (package_dir / "package_manifest.json").write_text(
        json.dumps(package_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    zip_path = out_dir / f"{book['id']}-package.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(package_dir.iterdir()):
            zf.write(f, arcname=f.name)

    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Package a QA-passed book's final deliverables")
    parser.add_argument("--id", required=True)
    args = parser.parse_args()

    book = find_book(args.id)
    if book is None:
        raise SystemExit(f"Book '{args.id}' not found in books.yaml")
    if book["status"] != "qa_passed":
        raise SystemExit(f"Book '{args.id}' has status '{book['status']}', expected 'qa_passed'")

    zip_path = package_book(book)
    print(f"Wrote {zip_path}")


if __name__ == "__main__":
    main()
