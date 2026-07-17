"""Package a classic or bilingual book's generated content as a
Kindle-ready reflowable EPUB (format: "ebook" in books.yaml).

Not available for type=lowcontent (planners/workbooks are fixed-layout
print products — see common/queue.py validation) or for the "ebook" format
before generated_content.json / bilingual_content.json exists.
"""

from __future__ import annotations

import argparse
import json
import re
import uuid
from pathlib import Path

from ebooklib import epub

_STYLE = """
body { font-size: 1em; line-height: 1.6; }
.ar { direction: rtl; unicode-bidi: embed; font-family: serif; text-align: justify; }
.en { direction: ltr; unicode-bidi: embed; font-family: serif; text-align: justify; }
h1, h2 { text-align: center; }
.annotations { font-size: 0.85em; border-top: 1px solid #999; margin-top: 1.5em; padding-top: 0.8em; }
.glossary dt { font-weight: bold; margin-top: 0.6em; }
"""


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def _new_book(book: dict) -> epub.EpubBook:
    epub_book = epub.EpubBook()
    epub_book.set_identifier(f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_DNS, book['id'])}")
    epub_book.set_title(book.get("title_en") or book["title_ar"])
    epub_book.set_language("ar")
    if book.get("author_ar"):
        epub_book.add_author(book["author_ar"])
    return epub_book


def _add_stylesheet(epub_book: epub.EpubBook) -> epub.EpubItem:
    css = epub.EpubItem(uid="style", file_name="style/main.css", media_type="text/css", content=_STYLE)
    epub_book.add_item(css)
    return css


def _html_chapter(uid: str, title: str, body_html: str, lang: str, css: epub.EpubItem) -> epub.EpubHtml:
    ch = epub.EpubHtml(title=title, file_name=f"{uid}.xhtml", lang=lang)
    dir_attr = "rtl" if lang == "ar" else "ltr"
    ch.content = f'<html dir="{dir_attr}"><body>{body_html}</body></html>'
    ch.add_item(css)
    return ch


def build_epub_from_classic(book: dict, out_dir: Path) -> Path:
    content = json.loads((out_dir / "generated_content.json").read_text(encoding="utf-8"))
    epub_book = _new_book(book)
    css = _add_stylesheet(epub_book)
    chapters: list[epub.EpubHtml] = []

    intro_html = "<h1>المقدمة</h1>" + "".join(
        f'<p class="ar">{p}</p>' for p in _paragraphs(content["introduction"])
    )
    intro = _html_chapter("intro", "المقدمة", intro_html, "ar", css)
    epub_book.add_item(intro)
    chapters.append(intro)

    for i, ch in enumerate(content["chapters"]):
        body = f'<h2>{ch["heading"]}</h2>' + "".join(
            f'<p class="ar">{p}</p>' for p in _paragraphs(ch["body"])
        )
        if ch.get("annotations"):
            body += '<div class="annotations"><h3>حواشٍ</h3><ol>' + "".join(
                f'<li><strong>{n["term"]}:</strong> {n["note"]}</li>' for n in ch["annotations"]
            ) + "</ol></div>"
        item = _html_chapter(f"chapter_{i}", ch["heading"], body, "ar", css)
        epub_book.add_item(item)
        chapters.append(item)

    glossary_html = "<h1>معجم المصطلحات</h1><dl>" + "".join(
        f'<dt class="ar">{g["term"]}</dt><dd class="ar">{g["definition"]}</dd>'
        for g in sorted(content.get("glossary", []), key=lambda g: g.get("term", ""))
    ) + "</dl>"
    glossary = _html_chapter("glossary", "معجم المصطلحات", glossary_html, "ar", css)
    epub_book.add_item(glossary)
    chapters.append(glossary)

    return _finalize(epub_book, chapters, book, out_dir)


def build_epub_from_bilingual(book: dict, out_dir: Path) -> Path:
    content = json.loads((out_dir / "bilingual_content.json").read_text(encoding="utf-8"))
    epub_book = _new_book(book)
    css = _add_stylesheet(epub_book)
    chapters: list[epub.EpubHtml] = []

    preface_html = "<h1>Translator's Preface</h1>" + "".join(
        f'<p class="en">{p}</p>' for p in _paragraphs(content["translator_preface_en"])
    )
    preface = _html_chapter("preface", "Translator's Preface", preface_html, "en", css)
    epub_book.add_item(preface)
    chapters.append(preface)

    for i, ch in enumerate(content["chapters"]):
        body = f'<h2 class="en">{ch["heading_en"]}</h2><h2 class="ar">{ch["heading"]}</h2>'
        for en_p, ar_p in zip(ch["paragraphs_en"], ch["paragraphs_ar"]):
            body += f'<p class="en">{en_p}</p><p class="ar">{ar_p}</p>'
        if ch.get("annotations"):
            body += '<div class="annotations ar"><h3>حواشٍ</h3><ol>' + "".join(
                f'<li><strong>{n["term"]}:</strong> {n["note"]}</li>' for n in ch["annotations"]
            ) + "</ol></div>"
        item = _html_chapter(f"chapter_{i}", ch["heading_en"], body, "en", css)
        epub_book.add_item(item)
        chapters.append(item)

    glossary_html = "<h1>Glossary</h1><dl>" + "".join(
        f'<dt class="ar">{g["term"]}</dt><dd class="ar">{g["definition"]}</dd>'
        for g in sorted(content.get("glossary", []), key=lambda g: g.get("term", ""))
    ) + "</dl>"
    glossary = _html_chapter("glossary", "Glossary", glossary_html, "ar", css)
    epub_book.add_item(glossary)
    chapters.append(glossary)

    return _finalize(epub_book, chapters, book, out_dir)


def _finalize(epub_book: epub.EpubBook, chapters: list[epub.EpubHtml], book: dict, out_dir: Path) -> Path:
    epub_book.toc = tuple(epub.Link(c.file_name, c.title, c.file_name) for c in chapters)
    epub_book.add_item(epub.EpubNcx())
    epub_book.add_item(epub.EpubNav())
    epub_book.spine = ["nav", *chapters]

    out_path = out_dir / f"{book['id']}.epub"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(out_path), epub_book)
    return out_path


def generate_ebook(book: dict, out_dir: Path) -> Path:
    if book["type"] == "classic":
        return build_epub_from_classic(book, out_dir)
    if book["type"] == "bilingual":
        return build_epub_from_bilingual(book, out_dir)
    raise ValueError(f"No ebook packager for type '{book['type']}'")


def main() -> None:
    parser = argparse.ArgumentParser(description="Package a book's generated content as an EPUB")
    parser.add_argument("--dir", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--title-en", default="")
    parser.add_argument("--author", default="")
    parser.add_argument("--type", choices=["classic", "bilingual"], required=True)
    args = parser.parse_args()

    book = {
        "id": args.id,
        "title_ar": args.title,
        "title_en": args.title_en,
        "author_ar": args.author,
        "type": args.type,
    }
    out = generate_ebook(book, Path(args.dir))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
