"""Clean a raw ingested text and split it into chapters.

Reads out_dir/raw.txt, writes out_dir/chapters.json:
    [{"heading": "...", "body": "..."}, ...]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from common.arabic_text import clean_arabic_text, split_into_chapters


def clean_book(book: dict, out_dir: Path) -> Path:
    raw_path = out_dir / "raw.txt"
    if not raw_path.exists():
        raise FileNotFoundError(f"{raw_path} not found — run ingest first")

    raw = raw_path.read_text(encoding="utf-8")
    cleaned = clean_arabic_text(raw, strip_diacritics_=False, strip_tatweel_=True)

    chapters_cfg = book.get("chapters", "auto")
    if chapters_cfg == "auto":
        chapters = split_into_chapters(cleaned)
    else:
        pattern = re.compile(chapters_cfg, re.MULTILINE)
        matches = list(pattern.finditer(cleaned))
        chapters = []
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(cleaned)
            chapters.append({"heading": m.group().strip(), "body": cleaned[start:end].strip()})
        if not chapters:
            chapters = [{"heading": "النص الكامل", "body": cleaned}]

    dest = out_dir / "chapters.json"
    dest.write_text(json.dumps(chapters, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean and chapter-split an ingested text")
    parser.add_argument("--dir", required=True, help="Book working directory (contains raw.txt)")
    parser.add_argument("--chapters", default="auto", help='"auto" or a regex heading pattern')
    args = parser.parse_args()

    dest = clean_book({"chapters": args.chapters}, Path(args.dir))
    print(f"Wrote {dest}")


if __name__ == "__main__":
    main()
