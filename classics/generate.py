"""Generate original editorial content for a classic Arabic text via the
Claude API: a ~1,500-word introduction, per-chapter annotations, and a
glossary of difficult terms.

The public-domain source text itself is never rewritten — only new,
original editorial material is generated around it (introduction,
footnote-style annotations, glossary), which is what KDP requires for a
public-domain reprint to be a legitimate value-added edition.

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
INTRO_TARGET_WORDS = 1500
INTRO_MIN_WORDS = 1400
MAX_RETRIES = 3
MAX_CHAPTERS_FOR_CONTEXT = 40  # cap prompt size for very long works


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
            return "".join(block.text for block in resp.content if block.type == "text").strip()
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


def generate_introduction(
    client: anthropic.Anthropic,
    title_ar: str,
    author_ar: str,
    chapters: list[dict],
) -> str:
    toc = "\n".join(f"- {c['heading']}" for c in chapters[:MAX_CHAPTERS_FOR_CONTEXT])
    excerpt = chapters[0]["body"][:1200] if chapters else ""

    system = (
        "أنت محرر أدبي وأكاديمي متخصص في التراث العربي الكلاسيكي، تكتب مقدمات "
        "تحليلية أصيلة لطبعات جديدة من نصوص تراثية تقع في الملكية العامة. "
        "أسلوبك رصين وواضح، يخدم القارئ المعاصر دون تبسيط مخل. لا تكرر نص "
        "الكتاب الأصلي، بل قدّم قراءة نقدية جديدة: سياق تأليف الكتاب، سيرة "
        "موجزة للمؤلف، أهمية الكتاب في تاريخه الفكري، وخريطة لموضوعاته."
    )
    user = (
        f"اكتب مقدمة أصلية لطبعة جديدة من كتاب \"{title_ar}\" "
        f"لمؤلفه {author_ar or 'مؤلف مجهول'}.\n\n"
        f"فهرس الفصول:\n{toc}\n\n"
        f"مقتطف من بداية النص للاستئناس بأسلوب الكتاب (لا تقتبس منه حرفيًا):\n"
        f"{excerpt}\n\n"
        f"المطلوب: مقدمة تحليلية أصيلة بالكامل بلغة عربية فصيحة، طولها "
        f"تقريبًا {INTRO_TARGET_WORDS} كلمة، مقسّمة إلى فقرات مترابطة بعناوين "
        f"فرعية داخلية عند الحاجة. لا تضع عنوانًا رئيسيًا للمقدمة نفسها "
        f"(سيُضاف لاحقًا)، ابدأ مباشرة بالنص."
    )

    text = _call(client, system, user, max_tokens=4096)
    wc = word_count(text)
    if wc < INTRO_MIN_WORDS:
        followup = (
            f"النص الذي كتبته يحتوي على {wc} كلمة فقط، والمطلوب حوالي "
            f"{INTRO_TARGET_WORDS} كلمة. أعد كتابة المقدمة كاملة بنفس الأسلوب "
            f"مع توسيع التحليل (السياق التاريخي، المنهج، الأثر اللاحق للكتاب) "
            f"حتى تبلغ الطول المطلوب."
        )
        text = _call(client, system, user + "\n\n" + followup, max_tokens=4096)
    return text


def generate_chapter_annotations(
    client: anthropic.Anthropic, chapter: dict, title_ar: str
) -> list[dict]:
    system = (
        "أنت محقق نصوص تراثية عربية. مهمتك إضافة حواشٍ توضيحية موجزة "
        "(تعليقات) على فصل من كتاب تراثي، لتفسير المصطلحات الصعبة أو "
        "الإشارات التاريخية أو الدينية أو الأدبية التي قد تخفى على القارئ "
        "المعاصر. أعد النتيجة بصيغة JSON فقط، بدون أي نص إضافي."
    )
    user = (
        f'من كتاب "{title_ar}"، الفصل بعنوان "{chapter["heading"]}":\n\n'
        f'{chapter["body"][:6000]}\n\n'
        "استخرج بين 3 و8 حواشٍ توضيحية لأهم المصطلحات أو الإشارات في هذا "
        "الفصل. أعد النتيجة بصيغة JSON: قائمة من كائنات "
        '{"term": "...", "note": "..."} فقط، بدون أي شرح إضافي خارج JSON.'
    )
    raw = _call(client, system, user, max_tokens=2048, effort="medium")
    return _parse_json_array(raw)


def generate_glossary(client: anthropic.Anthropic, chapters: list[dict], title_ar: str) -> list[dict]:
    sample = "\n\n".join(c["body"][:1500] for c in chapters[:MAX_CHAPTERS_FOR_CONTEXT])
    system = (
        "أنت محقق نصوص تراثية عربية تُعِدّ معجمًا (قائمة مصطلحات) لطبعة "
        "جديدة من كتاب تراثي، لمساعدة القارئ المعاصر على فهم المفردات "
        "الفصيحة النادرة أو الاصطلاحات القديمة. أعد النتيجة بصيغة JSON فقط."
    )
    user = (
        f'من نص كتاب "{title_ar}":\n\n{sample}\n\n'
        "استخرج 25 إلى 40 مصطلحًا يحتاج القارئ المعاصر إلى شرح لها (مفردات "
        "فصيحة نادرة، مصطلحات فقهية أو أدبية أو تاريخية)، مرتبة أبجديًا. "
        'أعد النتيجة بصيغة JSON فقط: قائمة من كائنات {"term": "...", '
        '"definition": "..."}، بدون أي نص خارج JSON.'
    )
    raw = _call(client, system, user, max_tokens=4096, effort="medium")
    return _parse_json_array(raw)


def _parse_json_array(raw: str) -> list[dict]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model did not return valid JSON: {exc}\n---\n{raw}") from exc
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array")
    return data


def generate_book_content(book: dict, out_dir: Path) -> Path:
    chapters_path = out_dir / "chapters.json"
    chapters = json.loads(chapters_path.read_text(encoding="utf-8"))

    client = _client()
    title_ar = book["title_ar"]
    author_ar = book.get("author_ar", "")

    introduction = generate_introduction(client, title_ar, author_ar, chapters)

    annotated_chapters = []
    for chapter in chapters:
        notes = generate_chapter_annotations(client, chapter, title_ar)
        annotated_chapters.append({**chapter, "annotations": notes})

    glossary = generate_glossary(client, chapters, title_ar)

    content = {
        "introduction": introduction,
        "introduction_word_count": word_count(introduction),
        "chapters": annotated_chapters,
        "glossary": glossary,
    }
    dest = out_dir / "generated_content.json"
    dest.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate intro/annotations/glossary via Claude API")
    parser.add_argument("--dir", required=True, help="Book working directory (contains chapters.json)")
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", default="")
    args = parser.parse_args()

    dest = generate_book_content(
        {"title_ar": args.title, "author_ar": args.author}, Path(args.dir)
    )
    print(f"Wrote {dest}")


if __name__ == "__main__":
    main()
