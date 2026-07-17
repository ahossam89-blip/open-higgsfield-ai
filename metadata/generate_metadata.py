"""Generate KDP listing metadata (title, subtitle, 7 keywords, categories,
description) for a book via the Claude API.

Requires ANTHROPIC_API_KEY in the environment.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import anthropic

DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")
MAX_RETRIES = 3
REQUIRED_FIELDS = ("title", "subtitle", "keywords", "categories", "description")


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
    metadata generation — the introduction for classics, or the spec for
    low-content books."""
    if book["type"] == "classic":
        content_path = out_dir / "generated_content.json"
        if content_path.exists():
            content = json.loads(content_path.read_text(encoding="utf-8"))
            intro = content.get("introduction", "")
            chapter_titles = "، ".join(c["heading"] for c in content.get("chapters", [])[:15])
            return f"مقدمة الكتاب (مقتطف):\n{intro[:2000]}\n\nعناوين الفصول: {chapter_titles}"
        return ""
    spec = book.get("spec", {})
    return f"نوع المحتوى: {book.get('generator')}\nمواصفات: {json.dumps(spec, ensure_ascii=False)}"


def generate_metadata(book: dict, out_dir: Path) -> dict:
    client = _client()
    summary = _content_summary(book, out_dir)

    system = (
        "أنت خبير في تحسين قوائم النشر على منصة Amazon KDP للكتب العربية. "
        "تكتب عناوين وأوصافًا وكلمات مفتاحية تزيد من ظهور الكتاب في نتائج "
        "البحث دون مبالغة أو تضليل. أعد ردك بصيغة JSON فقط، بدون أي نص خارج JSON."
    )
    user = (
        f"كتاب بعنوان مبدئي \"{book['title_ar']}\""
        + (f" للمؤلف {book['author_ar']}" if book.get("author_ar") else "")
        + f"\n\nملخص المحتوى:\n{summary}\n\n"
        "أنشئ بيانات النشر التالية بصيغة JSON فقط:\n"
        "{\n"
        '  "title": "عنوان جذاب ودقيق (بدون معلومات مضللة)",\n'
        '  "subtitle": "عنوان فرعي يوضح القيمة المضافة للطبعة",\n'
        '  "keywords": ["سبع كلمات أو عبارات مفتاحية بحثية مختلفة عن العنوان"],\n'
        '  "categories": ["فئتان إلى ثلاث فئات KDP الأنسب بالإنجليزية بصيغة '
        'Amazon BISAC، مثل Fiction > Classics"],\n'
        '  "description": "وصف تسويقي بالعربية بطول 150-250 كلمة لصفحة المنتج"\n'
        "}\n"
        "التزم بسبع كلمات مفتاحية بالضبط في مصفوفة keywords."
    )

    data = _call_json(client, system, user)
    if len(data.get("keywords", [])) != 7:
        # One corrective retry asking explicitly for exactly 7.
        data = _call_json(
            client, system,
            user + f"\n\nملاحظة: أعدت {len(data.get('keywords', []))} كلمات مفتاحية فقط. "
            "يجب أن تكون القائمة 7 كلمات/عبارات بالضبط، لا أكثر ولا أقل.",
        )

    dest = out_dir / "metadata.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate KDP metadata via Claude API")
    parser.add_argument("--dir", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", default="")
    parser.add_argument("--type", default="classic", choices=["classic", "low-content"])
    args = parser.parse_args()

    book = {"title_ar": args.title, "author_ar": args.author, "type": args.type}
    data = generate_metadata(book, Path(args.dir))
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
