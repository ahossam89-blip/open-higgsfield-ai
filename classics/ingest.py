"""Download and lightly extract a public-domain Arabic source text.

Supports plain-text URLs (e.g. Project Gutenberg .txt) and simple HTML pages
(extracts visible text via BeautifulSoup, dropping script/style/nav noise).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import requests
from bs4 import BeautifulSoup

USER_AGENT = "arabic-kdp-book-factory/1.0 (+https://github.com/)"
TIMEOUT_SECS = 60


class IngestError(RuntimeError):
    pass


def fetch_raw(url: str, timeout: int = TIMEOUT_SECS) -> bytes:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def extract_text(raw: bytes, fmt: str, encoding: str = "utf-8") -> str:
    if fmt == "text":
        return raw.decode(encoding, errors="replace")
    if fmt == "html":
        soup = BeautifulSoup(raw.decode(encoding, errors="replace"), "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        lines = [ln.strip() for ln in text.splitlines()]
        return "\n".join(ln for ln in lines if ln)
    raise IngestError(f"Unsupported source format '{fmt}'")


def ingest_book(book: dict, out_dir: Path, force: bool = False) -> Path:
    """Fetch a book's source per its books.yaml `source` block and save the
    raw extracted text to out_dir/raw.txt. Returns the path written.

    Idempotent: if out_dir/raw.txt already exists, skips the network fetch
    and returns the existing file (pass force=True to re-fetch) — this is
    what makes a resumed/retried pipeline run cheap and resilient to a
    transient network failure on a later stage.
    """
    dest = out_dir / "raw.txt"
    if dest.exists() and not force:
        return dest

    source = book.get("source")
    if not source or "url" not in source:
        raise IngestError(f"Book '{book['id']}' has no source.url configured")

    out_dir.mkdir(parents=True, exist_ok=True)
    raw = fetch_raw(source["url"])
    text = extract_text(raw, source.get("format", "text"), source.get("encoding", "utf-8"))

    dest.write_text(text, encoding="utf-8")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a public-domain Arabic source text")
    parser.add_argument("--url", required=True)
    parser.add_argument("--format", choices=["text", "html"], default="text")
    parser.add_argument("--encoding", default="utf-8")
    parser.add_argument("--out", required=True, help="Output directory")
    args = parser.parse_args()

    book = {"id": "cli", "source": {"url": args.url, "format": args.format, "encoding": args.encoding}}
    dest = ingest_book(book, Path(args.out))
    print(f"Wrote {dest}")


if __name__ == "__main__":
    main()
