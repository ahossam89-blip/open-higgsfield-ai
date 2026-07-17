"""Generate KDP listing metadata (title, subtitle, 7 keywords, 2 categories,
description, series line) for a book via the Claude API, grounded in real
search-demand signal from keywords/scrape_amazon.py where available.

Requires ANTHROPIC_API_KEY in the environment. Set AMAZON_MARKETPLACE_ID to
enable autocomplete-suggestion scraping (see keywords/scrape_amazon.py);
without it, only competitor-listing-title scraping is attempted, and if
that also fails (e.g. no network), metadata generation still proceeds on
Claude's own knowledge alone.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import anthropic

from keywords.scrape_amazon import get_keyword_candidates

DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")
MAX_RETRIES = 3
REQUIRED_FIELDS = ("title", "subtitle", "keywords", "categories", "description")
NUM_KEYWORDS = 7
NUM_CATEGORIES = 2


def _client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=api_key)


def _call_json(client: anthropic.Anthropic, system: str, user: str) -> dict:
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.messages.create(
                model=DEFAULT_MODEL,
                max_tokens=1500,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            if resp.stop_reason == "refusal":
                raise RuntimeError(f"Claude declined the request: {resp.stop_details}")
            raw = "".join(b.text for b in resp.content if b.type == "text").strip()
            return _parse_json_object(raw)
        except (anthropic.RateLimitError, anthropic.APIConnectionError, ValueError) as exc:
            last_err = exc
            time.sleep(2 ** attempt)
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                last_err = exc
                time.sleep(2 ** attempt)
            else:
                raise
    raise RuntimeError(f"Claude API metadata call failed after {MAX_RETRIES} attempts: {last_err}")


def _parse_json_object(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        raise ValueError(f"Model response missing fields: {missing}")
    return data


def _content_summary(book: dict, out_dir: Path) -> str:
    """Pull a short summary of the book's actual content to ground the
    metadata generation — the introduction for classics, the translator's
    preface + chapter list for bilingual editions, or the spec for
    low-content books."""
    if book["type"] == "classic":
        content_path = out_dir / "generated_content.json"
        if content_path.exists():
            content = json.loads(content_path.read_text(encoding="utf-8"))
            intro = content.get("introduction", "")
            chapter_titles = "، ".join(c["heading"] for c in content.get("chapters", [])[:15])
            return f"مقدمة الكتاب (مقتطف):\n{intro[:2000]}\n\nعناوين الفصول: {chapter_titles}"
        return ""

    if book["type"] == "bilingual":
        content_path = out_dir / "bilingual_content.json"
        if content_path.exists():
            content = json.loads(content_path.read_text(encoding="utf-8"))
            preface = content.get("translator_preface_en", "")
            chapter_titles = "، ".join(c["heading"] for c in content.get("chapters", [])[:15])
            return (
                f"طبعة ثنائية اللغة (عربي-إنجليزي). مقدمة المترجم (مقتطف):\n{preface[:1200]}\n\n"
                f"عناوين الفصول: {chapter_titles}"
            )
        return ""

    spec = book.get("spec", {})
    return f"نوع المحتوى: {book.get('generator')}\nمواصفات: {json.dumps(spec, ensure_ascii=False)}"


def _research_context(book: dict) -> str:
    """Best-effort Amazon keyword-research signal (see
    keywords/scrape_amazon.py) — never raises; returns an empty-results
    note if scraping is unavailable (no network, robots.txt disallow, etc.),
    in which case Claude falls back to its own knowledge."""
    candidates = get_keyword_candidates(
        book["title_ar"], mid=os.environ.get("AMAZON_MARKETPLACE_ID") or None
    )
    if not candidates["autocomplete"] and not candidates["competitor_titles"]:
        return "لا تتوفر بيانات بحث حية من أمازون لهذه الجلسة."
    lines = []
    if candidates["autocomplete"]:
        lines.append("اقتراحات البحث التلقائي على أمازون: " + "، ".join(candidates["autocomplete"]))
    if candidates["competitor_titles"]:
        lines.append("عناوين كتب منافسة في نتائج البحث: " + "، ".join(candidates["competitor_titles"]))
    return "\n".join(lines)


def generate_metadata(book: dict, out_dir: Path, force: bool = False) -> dict:
    """Idempotent: skips the Claude API call and returns the existing
    output/<id>/metadata.json if it's already there."""
    dest = out_dir / "metadata.json"
    if dest.exists() and not force:
        return json.loads(dest.read_text(encoding="utf-8"))

    client = _client()
    summary = _content_summary(book, out_dir)
    research = _research_context(book)

    system = (
        "أنت خبير في تحسين قوائم النشر على منصة Amazon KDP للكتب العربية. "
        "تكتب عناوين وأوصافًا وكلمات مفتاحية تزيد من ظهور الكتاب في نتائج "
        "البحث دون مبالغة أو تضليل، مستعينًا ببيانات بحث حقيقية عند توفرها. "
        "أعد ردك بصيغة JSON فقط، بدون أي نص خارج JSON."
    )
    user = (
        f"كتاب بعنوان مبدئي \"{book['title_ar']}\""
        + (f" للمؤلف {book['author_ar']}" if book.get("author_ar") else "")
        + (f"\nالسلسلة: {book['series']}" if book.get("series") else "")
        + f"\n\nملخص المحتوى:\n{summary}\n\nبيانات بحث السوق:\n{research}\n\n"
        "أنشئ بيانات النشر التالية بصيغة JSON فقط:\n"
        "{\n"
        '  "title": "عنوان جذاب ودقيق (بدون معلومات مضللة)",\n'
        '  "subtitle": "عنوان فرعي يوضح القيمة المضافة للطبعة",\n'
        f'  "keywords": ["{NUM_KEYWORDS} كلمات أو عبارات مفتاحية بحثية مختلفة عن العنوان، '
        'مستفادة من بيانات البحث أعلاه عند توفرها"],\n'
        f'  "categories": ["{NUM_CATEGORIES} فئتان من فئات KDP الأنسب بالإنجليزية بصيغة '
        'Amazon BISAC، مثل Fiction > Classics"],\n'
        '  "description": "وصف تسويقي بالعربية بطول 150-250 كلمة لصفحة المنتج",\n'
        '  "series_line": "جملة قصيرة تصف موضع هذا الكتاب ضمن سلسلته وتربطه بالكتب الأخرى فيها '
        '(اتركها فارغة \\"\\" إذا لم يكن الكتاب جزءًا من سلسلة)"\n'
        "}\n"
        f"التزم بـ {NUM_KEYWORDS} كلمات مفتاحية بالضبط في مصفوفة keywords، "
        f"وبـ {NUM_CATEGORIES} فئتين بالضبط في مصفوفة categories."
    )

    data = _call_json(client, system, user)
    if len(data.get("keywords", [])) != NUM_KEYWORDS or len(data.get("categories", [])) != NUM_CATEGORIES:
        # One corrective retry, explicit about which counts were wrong.
        data = _call_json(
            client, system,
            user + f"\n\nملاحظة: ردك السابق كان به {len(data.get('keywords', []))} كلمة مفتاحية "
            f"و{len(data.get('categories', []))} فئة. المطلوب بالضبط {NUM_KEYWORDS} كلمات مفتاحية "
            f"و{NUM_CATEGORIES} فئتين، لا أكثر ولا أقل.",
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate KDP metadata via Claude API")
    parser.add_argument("--dir", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", default="")
    parser.add_argument("--type", default="classic", choices=["classic", "bilingual", "lowcontent"])
    args = parser.parse_args()

    book = {"title_ar": args.title, "author_ar": args.author, "type": args.type}
    data = generate_metadata(book, Path(args.dir))
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
