"""Download the open-licensed (SIL OFL) Arabic fonts used by the typesetting
templates into assets/fonts/. Run once after cloning:

    python -m scripts.fetch_fonts

Fonts are not vendored in git (binary, and Google Fonts already serves
versioned raw files), so CI runs this before typesetting any book.
"""

from __future__ import annotations

from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = REPO_ROOT / "assets" / "fonts"

# Raw, permanent URLs into the google/fonts OFL-licensed repository.
FONT_SOURCES = {
    "Amiri-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/amiri/Amiri-Regular.ttf",
    "Amiri-Bold.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/amiri/Amiri-Bold.ttf",
    "Cairo-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/cairo/Cairo%5Bslnt%2Cwght%5D.ttf",
    "Cairo-Bold.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/cairo/Cairo%5Bslnt%2Cwght%5D.ttf",
    "NotoNaskhArabic-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/notonaskharabic/NotoNaskhArabic%5Bwght%5D.ttf",
}

TIMEOUT_SECS = 60


def fetch_fonts(force: bool = False) -> None:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    for filename, url in FONT_SOURCES.items():
        dest = FONTS_DIR / filename
        if dest.exists() and not force:
            print(f"skip (exists): {filename}")
            continue
        print(f"downloading {filename} ...")
        resp = requests.get(url, timeout=TIMEOUT_SECS)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        print(f"  -> {dest} ({len(resp.content)} bytes)")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Download open Arabic fonts for typesetting")
    parser.add_argument("--force", action="store_true", help="Re-download even if already present")
    args = parser.parse_args()
    fetch_fonts(force=args.force)


if __name__ == "__main__":
    main()
