"""Arabic text cleaning / normalization utilities shared by the classics
ingest pipeline (and available to the low-content generators for labels).

These are deliberately conservative: they fix whitespace, punctuation,
digit, and encoding noise that is common in scraped/OCR'd public-domain
Arabic texts, without silently rewriting the author's orthography (e.g. we
do NOT strip diacritics — that's a content decision left to the caller via
`strip_diacritics=True`).
"""

from __future__ import annotations

import re
import unicodedata

# Arabic diacritics (tashkeel) + tatweel (kashida) block.
_DIACRITICS = "ًٌٍَُِّْٰٕٖٓٔٗ٘"
_TATWEEL = "ـ"
_DIACRITIC_RE = re.compile(f"[{_DIACRITICS}]")
_TATWEEL_RE = re.compile(_TATWEEL)

# Eastern Arabic-Indic digits -> Western digits.
_EASTERN_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_WESTERN_DIGITS = "0123456789"
_DIGIT_MAP = str.maketrans(_EASTERN_DIGITS, _WESTERN_DIGITS)

# Common scraped-text noise.
_MULTI_SPACE_RE = re.compile(r"[ \t ]+")
_MULTI_BLANK_LINE_RE = re.compile(r"\n{3,}")
_TRAILING_WS_RE = re.compile(r"[ \t]+\n")

# Normalize common punctuation variants to their Arabic presentation forms.
_PUNCT_MAP = {
    "?": "؟",
    ",": "،",
    ";": "؛",
    "–": "-",   # en dash
    "—": "—",  # keep em dash
    "“": "«",  # “ -> «
    "”": "»",  # ” -> »
    "﻿": "",        # BOM
}


def normalize_digits_to_western(text: str) -> str:
    return text.translate(_DIGIT_MAP)


def strip_diacritics(text: str) -> str:
    return _DIACRITIC_RE.sub("", text)


def strip_tatweel(text: str) -> str:
    return _TATWEEL_RE.sub("", text)


# Alef variants (hamza-above, hamza-below, madda, wasla) collapsed to the
# bare alef. This is a deliberate editorial normalization for scanned /
# OCR'd public-domain sources with inconsistent scribal hamza placement —
# it does NOT touch hamza on waw/yeh (ؤ ئ) or the standalone hamza (ء),
# only the four alef letterforms. Disable per-book via
# books.yaml `normalize.unify_alef: false` if the source's exact
# orthography must be preserved.
_ALEF_VARIANTS_RE = re.compile("[أإآٱ]")


def unify_alef_forms(text: str) -> str:
    return _ALEF_VARIANTS_RE.sub("ا", text)


def normalize_punctuation(text: str) -> str:
    for src, dst in _PUNCT_MAP.items():
        text = text.replace(src, dst)
    return text


def collapse_whitespace(text: str) -> str:
    text = _TRAILING_WS_RE.sub("\n", text)
    lines = [_MULTI_SPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = _MULTI_BLANK_LINE_RE.sub("\n\n", text)
    return text.strip() + "\n"


def clean_arabic_text(
    text: str,
    *,
    strip_diacritics_: bool = False,
    strip_tatweel_: bool = True,
    unify_alef: bool = True,
    normalize_digits: bool = True,
    normalize_form: str = "NFC",
) -> str:
    """Full normalization pipeline used before typesetting."""
    text = unicodedata.normalize(normalize_form, text)
    text = normalize_punctuation(text)
    if strip_tatweel_:
        text = strip_tatweel(text)
    if unify_alef:
        text = unify_alef_forms(text)
    if strip_diacritics_:
        text = strip_diacritics(text)
    if normalize_digits:
        text = normalize_digits_to_western(text)
    text = collapse_whitespace(text)
    return text


# A line is treated as a chapter heading if it matches common patterns used
# in classical Arabic texts: "الباب الأول", "الفصل الثاني", "الفصل: ...",
# a lone "بسم الله الرحمن الرحيم" divider, or a short standalone line in
# Arabic-Indic/Latin numerals prefixed by a known heading word.
_HEADING_WORDS = r"(?:الباب|الفصل|الكتاب|الجزء|المقالة|باب|فصل)"
_HEADING_RE = re.compile(
    rf"^\s*{_HEADING_WORDS}\s+(?:[ء-ي]+|\d+)\b.*$",
    re.MULTILINE,
)


def split_into_chapters(text: str) -> list[dict[str, str]]:
    """Split cleaned text into chapters using heading heuristics.

    Returns a list of {"heading": str, "body": str}. If no headings are
    found, the whole text becomes a single chapter titled "النص الكامل".
    """
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [{"heading": "النص الكامل", "body": text.strip()}]

    chapters: list[dict[str, str]] = []
    for i, m in enumerate(matches):
        heading = m.group().strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            chapters.append({"heading": heading, "body": body})
    return chapters or [{"heading": "النص الكامل", "body": text.strip()}]


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))
