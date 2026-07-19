"""Generate the English side of a bilingual Arabic/English edition via the
Claude API: a translator's preface, and a paragraph-aligned English
translation of each chapter.

Translation output is deliberately kept **paragraph-aligned** with the
source (same paragraph count, same order) — bilingual/typeset.py relies on
that alignment to force each paragraph pair onto a facing left/right page
spread. A translation that merges or splits paragraphs will still render,
but the facing-page pairing for that chapter will drift.

Requires ANTHROPIC_API_KEY in the environment.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import anthropic

from common.arabic_text import word_count

DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")
PREFACE_TARGET_WORDS = 900
MAX_RETRIES = 3
MAX_CHAPTERS_FOR_CONTEXT = 40


def _client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=api_key)


def _call(client: anthropic.Anthropic, system: str, user: str, max_tokens: int, effort: str = "high") -> str:
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.messages.create(
                model=DEFAULT_MODEL,
                max_tokens=max_tokens,
                thinking={"type": "adaptive"},
                output_config={"effort": effort},
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            if resp.stop_reason == "refusal":
                raise RuntimeError(f"Claude declined the request: {resp.stop_details}")
            return "".join(b.text for b in resp.content if b.type == "text").strip()
        except (anthropic.RateLimitError, anthropic.APIConnectionError) as exc:
            last_err = exc
            time.sleep(2 ** attempt)
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                last_err = exc
                time.sleep(2 ** attempt)
            else:
                raise
    raise RuntimeError(f"Claude API call failed after {MAX_RETRIES} attempts: {last_err}")


def generate_translator_preface(
    client: anthropic.Anthropic, title_ar: str, author_ar: str, chapters: list[dict]
) -> str:
    toc = "\n".join(f"- {c['heading']}" for c in chapters[:MAX_CHAPTERS_FOR_CONTEXT])
    system = (
        "You are an experienced literary translator writing a translator's "
        "preface for a new bilingual Arabic/English edition of a classical "
        "Arabic work. Your preface discusses your translation approach and "
        "philosophy, the challenges specific to this text, and what an "
        "English-language reader should understand about reading it "
        "alongside the Arabic original. It is original commentary, not a "
        "summary of the book's plot."
    )
    user = (
        f'Write a translator\'s preface for a new bilingual edition of "{title_ar}"'
        + (f" by {author_ar}" if author_ar else "")
        + f".\n\nTable of contents:\n{toc}\n\n"
        f"Target length: approximately {PREFACE_TARGET_WORDS} words, in clear "
        "English prose, organized into a few natural paragraphs (no heading — "
        "one will be added separately). Cover: your approach to balancing "
        "literal fidelity against readability, how you handled untranslatable "
        "or culturally specific terms (note that a glossary is provided "
        "separately in this edition), and why a facing-page bilingual format "
        "suits this text."
    )
    text = _call(client, system, user, max_tokens=2048, effort="high")
    wc = word_count(text)
    if wc < PREFACE_TARGET_WORDS - 150:
        text = _call(
            client, system,
            user + f"\n\nYour previous draft was only {wc} words; expand it to "
            f"approximately {PREFACE_TARGET_WORDS} words while keeping the same voice.",
            max_tokens=2048, effort="high",
        )
    return text


def translate_chapter(client: anthropic.Anthropic, chapter: dict, title_ar: str) -> dict:
    paragraphs = [p.strip() for p in chapter["body"].split("\n\n") if p.strip()]
    system = (
        "You are a professional literary translator producing the English "
        "side of a facing-page bilingual Arabic/English edition. Translate "
        "faithfully into clear literary English. CRITICAL: you must return "
        "exactly one English paragraph for every Arabic paragraph provided, "
        "in the same order — the paragraphs are typeset side by side, so "
        "merging or splitting paragraphs will break the facing-page layout. "
        "Respond with JSON only, no text outside the JSON."
    )
    numbered = "\n\n".join(f"[{i}] {p}" for i, p in enumerate(paragraphs))
    user = (
        f'From "{title_ar}", chapter "{chapter["heading"]}", translate this chapter '
        f"heading and each numbered Arabic paragraph into English.\n\n{numbered}\n\n"
        'Respond with JSON only: {"heading_en": "...", '
        '"paragraphs_en": ["translation of [0]", "translation of [1]", ...]}. '
        f"The paragraphs_en array must have exactly {len(paragraphs)} elements, "
        "in order, matching the numbered paragraphs one-to-one."
    )
    raw = _call(client, system, user, max_tokens=4096, effort="medium")
    data = json.loads(_strip_code_fence(raw))
    translated = data.get("paragraphs_en", [])
    if len(translated) != len(paragraphs):
        # One corrective retry, explicit about the mismatch.
        raw = _call(
            client, system,
            user + f"\n\nYour previous response had {len(translated)} paragraphs "
            f"but exactly {len(paragraphs)} are required — one per numbered "
            "source paragraph, in order.",
            max_tokens=4096, effort="medium",
        )
        data = json.loads(_strip_code_fence(raw))
        translated = data.get("paragraphs_en", [])

    return {
        "heading": chapter["heading"],
        "heading_en": data.get("heading_en", chapter["heading"]),
        "paragraphs_ar": paragraphs,
        "paragraphs_en": (translated + [""] * len(paragraphs))[: len(paragraphs)],
        "annotations": chapter.get("annotations", []),
    }


def _strip_code_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text


def translate_book(book: dict, out_dir: Path, force: bool = False) -> Path:
    """Idempotent: skips the (expensive, Claude-API-calling) translation
    entirely if out_dir/bilingual_content.json already exists."""
    dest = out_dir / "bilingual_content.json"
    if dest.exists() and not force:
        return dest

    chapters = json.loads((out_dir / "chapters.json").read_text(encoding="utf-8"))
    generated_path = out_dir / "generated_content.json"
    generated = json.loads(generated_path.read_text(encoding="utf-8")) if generated_path.exists() else {}
    annotations_by_heading = {
        c["heading"]: c.get("annotations", []) for c in generated.get("chapters", [])
    }
    for c in chapters:
        c["annotations"] = annotations_by_heading.get(c["heading"], [])

    client = _client()
    title_ar = book["title_ar"]
    author_ar = book.get("author_ar", "")

    preface_en = generate_translator_preface(client, title_ar, author_ar, chapters)
    translated_chapters = [translate_chapter(client, c, title_ar) for c in chapters]

    content = {
        "translator_preface_en": preface_en,
        "chapters": translated_chapters,
        "glossary": generated.get("glossary", []),
        "introduction_ar": generated.get("introduction", ""),
    }
    dest.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the English side of a bilingual edition")
    parser.add_argument("--dir", required=True, help="Book working directory (contains chapters.json)")
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", default="")
    args = parser.parse_args()

    dest = translate_book({"title_ar": args.title, "author_ar": args.author}, Path(args.dir))
    print(f"Wrote {dest}")


if __name__ == "__main__":
    main()
