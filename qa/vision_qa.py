"""Visual QA gate: rasterize a sample of interior pages plus the cover and
send them to the Claude API (vision) to catch defects invisible to
structural/content checks — broken or disconnected Arabic letterforms,
wrong RTL reading flow, missing-glyph ("tofu") boxes, dirty margins/bleed,
and misaligned annotations.

This is a genuinely blocking check: qa/run_qa.py treats a failed or errored
vision pass as an overall QA failure — "never package a failed book" means
a vision-QA error (e.g. a transient API failure) must not be treated as a
pass by default.

Rasterization uses PyMuPDF (no system `poppler`/`pdftoppm` dependency).
"""

from __future__ import annotations

import base64
import json
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
import fitz  # PyMuPDF

DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")
RASTER_DPI = 150
SAMPLE_PAGE_COUNT = 5
MAX_RETRIES = 3

SYSTEM_PROMPT = (
    "You are a meticulous print-production QA inspector for an Arabic-language "
    "Amazon KDP book (paperback/hardcover interior pages and a full-wrap cover). "
    "You are shown rasterized page images. For EACH image, check for:\n"
    "1. Connected Arabic letterforms — letters within a word must be properly "
    "joined (no broken/disconnected ligatures, no isolated-form glyphs used "
    "mid-word).\n"
    "2. Correct right-to-left reading flow for Arabic text (and, on a "
    "facing-page bilingual spread, correct left-to-right flow for the English "
    "side) — text must not appear reversed, mirrored, or out of order.\n"
    "3. No missing-glyph boxes ('tofu' — empty rectangles where a character "
    "failed to render) or obviously wrong/garbled characters.\n"
    "4. Clean margins and bleed — no unintended clipped text, no stray "
    "artifacts at the page edges, no content bleeding into the gutter.\n"
    "5. Annotations/footnotes (if visible) are aligned under a clear "
    "separator and not overlapping body text.\n\n"
    "Respond with JSON ONLY, no text outside the JSON, in this exact shape:\n"
    '{"pages": [{"label": "<the label given for this image>", "passed": true|false, '
    '"issues": ["short specific issue description", ...]}], '
    '"overall_passed": true|false, "summary": "one or two sentence overall verdict"}\n'
    "overall_passed must be false if ANY image has passed=false. Be strict — "
    "this gate exists specifically to catch defects a purely structural PDF "
    "check cannot see."
)


@dataclass
class VisionQAResult:
    ran: bool
    passed: bool
    summary: str
    per_image: list[dict] = field(default_factory=list)
    error: str = ""


def _client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=api_key)


def rasterize_page(pdf_path: Path, page_index: int, dpi: int = RASTER_DPI) -> bytes:
    doc = fitz.open(str(pdf_path))
    try:
        pix = doc[page_index].get_pixmap(dpi=dpi)
        return pix.tobytes("png")
    finally:
        doc.close()


def sample_interior_pages(pdf_path: Path, n: int = SAMPLE_PAGE_COUNT, seed: int | None = None) -> list[int]:
    doc = fitz.open(str(pdf_path))
    try:
        count = doc.page_count
    finally:
        doc.close()
    rng = random.Random(seed)
    if count <= n:
        return list(range(count))
    return sorted(rng.sample(range(count), n))


def _strip_code_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text


def _call_vision(client: anthropic.Anthropic, images: list[tuple[str, bytes]]) -> dict:
    content = [
        {
            "type": "text",
            "text": "Inspect the following labeled page images per the checklist in your system prompt.",
        }
    ]
    for label, png_bytes in images:
        content.append({"type": "text", "text": f"Label: {label}"})
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.standard_b64encode(png_bytes).decode("ascii"),
                },
            }
        )

    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.messages.create(
                model=DEFAULT_MODEL,
                max_tokens=2048,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
            )
            if resp.stop_reason == "refusal":
                raise RuntimeError(f"Claude declined the vision QA request: {resp.stop_details}")
            raw = "".join(b.text for b in resp.content if b.type == "text").strip()
            return json.loads(_strip_code_fence(raw))
        except (anthropic.RateLimitError, anthropic.APIConnectionError) as exc:
            last_err = exc
            time.sleep(2 ** attempt)
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                last_err = exc
                time.sleep(2 ** attempt)
            else:
                raise
    raise RuntimeError(f"Vision QA call failed after {MAX_RETRIES} attempts: {last_err}")


def run_vision_qa(
    interior_pdf: Path,
    cover_pdf: Path | None,
    out_dir: Path,
    seed: int | None = None,
) -> VisionQAResult:
    """Rasterize the sample + cover, run the Claude vision check, and save
    the rasterized images + raw verdict under out_dir/qa_report/ (used for
    the quarantine report on failure)."""
    qa_dir = out_dir / "qa_report"
    qa_dir.mkdir(parents=True, exist_ok=True)

    try:
        client = _client()
        images: list[tuple[str, bytes]] = []

        page_indices = sample_interior_pages(interior_pdf, seed=seed)
        for idx in page_indices:
            png_bytes = rasterize_page(interior_pdf, idx)
            label = f"interior page {idx + 1}"
            (qa_dir / f"interior_p{idx + 1}.png").write_bytes(png_bytes)
            images.append((label, png_bytes))

        if cover_pdf is not None and cover_pdf.exists():
            png_bytes = rasterize_page(cover_pdf, 0)
            label = "full-wrap cover"
            (qa_dir / "cover.png").write_bytes(png_bytes)
            images.append((label, png_bytes))

        verdict = _call_vision(client, images)
        (qa_dir / "vision_verdict.json").write_text(
            json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return VisionQAResult(
            ran=True,
            passed=bool(verdict.get("overall_passed", False)),
            summary=verdict.get("summary", ""),
            per_image=verdict.get("pages", []),
        )
    except Exception as exc:  # noqa: BLE001 - fail closed: any vision-QA error is a QA failure
        return VisionQAResult(ran=True, passed=False, summary="", error=str(exc))
