# Arabic KDP Publishing Factory

An automated pipeline that turns a queue (`books.yaml`) into print-ready
Amazon KDP packages — interior PDF(s), full-wrap cover PDF(s) per binding,
an EPUB where requested, and listing metadata — for three product lines:

- **Classics** (`classics/`) — public-domain Arabic texts re-published with
  an original Claude-generated introduction, chapter annotations, and
  glossary.
- **Bilingual** (`bilingual/`) — the same ingest/clean/generate pipeline as
  classics, plus a Claude-generated English translation and translator's
  preface, typeset as a true facing-page edition (English on left/verso
  pages, Arabic on right/recto pages, paired paragraph by paragraph).
- **Low-content** (`lowcontent/`) — parametric planners and Arabic
  handwriting/practice workbooks, generated programmatically (no AI text,
  just layout).

Each book can be produced in one or more **formats**: `paperback`,
`hardcover`, `ebook` (EPUB — classics/bilingual only). A weekly GitHub
Action processes the next queued book through the full pipeline and
attaches the results to a (draft) GitHub Release.

## Pipeline stages

Every book in `books.yaml` advances through a fixed state machine
(`common/queue.py`):

```
queued -> generated -> qa_passed -> packaged -> published
                  \
                   -> failed   (at the "generated" build step or the QA gate;
                                 see the book's `notes` field for why)
```

| Stage | What happens | Where |
|---|---|---|
| `queued` | Book is waiting to be processed. | — |
| `generated` | Interior content produced (ingest/clean/generate/translate/typeset), one cover PDF per print format, one EPUB if `ebook` is requested, and listing metadata. | `scripts/run_pipeline.py` → product-line `build.py` + `covers/` + `ebook/` + `metadata/` |
| `qa_passed` | Automated structural/content checks passed (PDF sizes match KDP geometry, spine width matches page count, word counts/glossary/paragraph-alignment sane, metadata complete). | `qa/run_qa.py` |
| `packaged` | Final per-format deliverables copied into `output/<id>/package/` and zipped. | `bookpack/package_book.py` |
| `published` | Attached to a GitHub Release. | `.github/workflows/weekly-book-factory.yml`, after the release is created |

## Directory layout

```
books.yaml              # the production queue (see schema below)
common/
  kdp_specs.py           # KDP trim sizes, margins/gutter, spine width, paperback + hardcover cover geometry
  queue.py                # books.yaml read/write/status-pipeline helpers
  arabic_text.py           # Arabic normalization (alef unification, tatweel, punctuation) + chapter-splitting
classics/
  ingest.py                # download a public-domain source text
  clean.py                  # normalize + split into chapters
  generate.py                # Claude API: intro, chapter annotations, glossary
  typeset.py                  # Jinja2 + WeasyPrint -> print-ready RTL interior PDF
  build.py                     # orchestrates the four steps above
  templates/book.html.j2, book.css
bilingual/
  translate.py              # Claude API: translator's preface + paragraph-aligned English translation
  typeset.py                  # Jinja2 + WeasyPrint -> facing-page interior PDF (English left / Arabic right)
  build.py                      # ingest/clean/generate (reused from classics/) -> translate -> typeset
  templates/bilingual_book.html.j2, bilingual_book.css
lowcontent/
  common/svg_utils.py       # tiny SVG page builder (RTL Arabic helpers)
  common/pdf_render.py       # SVG pages -> merged PDF
  planners/generate_planner.py     # weekly/monthly planner generator
  workbooks/generate_workbook.py    # letter-tracing workbook generator
covers/
  generate_cover.py         # full wrap (back|spine|front) cover; paperback (bleed) or hardcover (wrap+hinge)
ebook/
  generate_epub.py          # packages a classic/bilingual book's generated content as a reflowable EPUB
qa/
  run_qa.py                  # automated QA gate: PDF geometry, spine width, content sanity, metadata completeness
bookpack/
  package_book.py            # assembles + zips the final per-format deliverables (NOT named "packaging" —
                              # that collides with the PyPI `packaging` library, a transitive dependency of
                              # several other requirements here; see the comment in scripts/run_pipeline.py)
metadata/
  generate_metadata.py      # Claude API: title, subtitle, 7 keywords, categories, description
  export_csv.py               # compiles every book into upload_checklist.csv
scripts/
  fetch_fonts.py             # downloads OFL Arabic fonts into assets/fonts/
  run_pipeline.py             # end-to-end: next queued book -> generated -> qa_passed -> packaged
.github/workflows/weekly-book-factory.yml
```

## Setup

```bash
pip install -r requirements.txt
python -m scripts.fetch_fonts   # downloads Amiri, Cairo, Noto Naskh Arabic (OFL) into assets/fonts/
export ANTHROPIC_API_KEY=sk-ant-...
```

WeasyPrint needs a few system libraries for text shaping (Pango/Cairo/HarfBuzz):

```bash
# Debian/Ubuntu
sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info
```

(the GitHub Action installs these automatically.)

## Running the pipeline

Process the next `status: queued` book in `books.yaml` (classic, bilingual,
or lowcontent — the orchestrator dispatches automatically, and produces
every format listed in that book's `formats`):

```bash
python -m scripts.run_pipeline
```

Process a specific book, or preview what would run:

```bash
python -m scripts.run_pipeline --id kalila-wa-dimna
python -m scripts.run_pipeline --dry-run
```

This runs the book through `generated -> qa_passed -> packaged` (see
Pipeline stages above), writing to `output/<book_id>/`:
- `<id>-interior.pdf` — the manuscript PDF (KDP margins, trim size; shared
  across paperback and hardcover — only the cover differs by binding)
- `<id>-cover-paperback.pdf` / `<id>-cover-hardcover.pdf` — one full-wrap
  cover per requested print format, spine/wrap sized from the actual
  rendered page count
- `<id>.epub` — if `ebook` is a requested format (classic/bilingual only)
- `metadata.json` — title/subtitle/7 keywords/categories/description
- `manifest.json` — paths + computed KDP numbers (page count, spine width per format)
- `package/` and `<id>-package.zip` — the final upload-ready bundle (only
  produced once QA passes)

If any stage fails, the book's `status` becomes `failed` with a `notes`
field explaining why (a QA check name + detail, or a Python traceback for a
build error) — it is **not** silently left as `queued` or partially
advanced. `metadata/export_csv.py` (run automatically at the end of
`run_pipeline`) refreshes `output/upload_checklist.csv`, a one-row-per-book
KDP upload checklist across the whole queue.

Individual stages can also be run standalone — see `--help` on each module
(`classics/ingest.py`, `classics/clean.py`, `classics/generate.py`,
`classics/typeset.py`, `bilingual/translate.py`, `bilingual/typeset.py`,
`covers/generate_cover.py` (`--binding paperback|hardcover`),
`ebook/generate_epub.py`,
`lowcontent/planners/generate_planner.py`,
`lowcontent/workbooks/generate_workbook.py`,
`metadata/generate_metadata.py`, `qa/run_qa.py`, `bookpack/package_book.py`).

## `books.yaml` schema

See the commented header in `books.yaml` for the full field reference.
Summary:

| Field | Applies to | Notes |
|---|---|---|
| `id` | all | slug, used for `output/<id>/` and filenames |
| `type` | all | `classic` \| `bilingual` \| `lowcontent` |
| `title_ar` | all | working title (metadata generation may refine it) |
| `title_en` | bilingual | working English title for the running header; falls back to `title_ar` |
| `series` | all, optional | grouped in the upload checklist CSV |
| `formats` | all | list of `paperback` \| `hardcover` \| `ebook`. `ebook` is invalid for `lowcontent` (validated at load time) |
| `trim_size` | all | key into `common/kdp_specs.TRIM_SIZES`, e.g. `"6x9"` |
| `paper_type` | all | `white` \| `cream` \| `color` — affects spine width |
| `cover_style` | all, optional | `classic` \| `modern` \| `warm` palette, default `classic` |
| `status` | all | `queued` \| `generated` \| `qa_passed` \| `packaged` \| `published` \| `failed` |
| `source.url/format/encoding` | classic, bilingual | source text to ingest |
| `author_ar`, `chapters` | classic, bilingual | colophon author; `"auto"` or a regex heading pattern |
| `normalize.*` | classic, bilingual, optional | overrides for `common/arabic_text.clean_arabic_text` (`strip_diacritics`, `strip_tatweel`, `unify_alef`) |
| `generator` | lowcontent | `planner` \| `workbook` |
| `spec` | lowcontent | generator-specific params — see the generator module docstring |

## KDP specifics (`common/kdp_specs.py`)

- **Trim sizes**: the full KDP paperback catalogue (5x8 through 8.5x11, A4).
- **Gutter/margins**: KDP's no-bleed interior margin table by page count
  (0.375in–0.875in inside margin), plus configurable top/bottom/outside.
  `classics/typeset.py` and `bilingual/typeset.py` each render the interior
  twice: once to measure the actual page count, once more with the correct
  KDP margins for that count.
- **Spine width**: `page_count * factor`, factor per paper stock
  (white/cream/color), per KDP's published constants.
- **Paperback cover geometry**: `compute_cover_layout()` returns the full
  bleed sheet size and the back/spine/front panel boundaries. KDP's flat
  cover file is always laid out back-cover-left, spine-center,
  front-cover-right — a fixed print-production convention independent of
  the interior's reading direction.
- **Hardcover cover geometry**: `compute_hardcover_cover_layout()` uses the
  case-wrap layout instead of bleed — a 0.75in wrap on the outer edges, a
  0.75in hinge strip on each side of the spine, and a spine width that adds
  board thickness to the interior paper-block spine. These constants are
  transcribed from KDP's published hardcover guidance and are
  **approximate** — re-verify against KDP's current hardcover cover
  calculator before a real print run.
- Spine text is only placed if `page_count >= 100`, per KDP's own rule.

## Facing-page bilingual typesetting

`bilingual/typeset.py` does **not** try to guess where each language's text
will land and hope the pages line up — that drifts the moment a translation
runs longer or shorter than its source paragraph. Instead it forces exact
pairing with CSS Paged Media: every English paragraph section gets
`page-break-before: left`, every corresponding Arabic paragraph section gets
`page-break-before: right`. WeasyPrint inserts a blank page automatically
whenever one side needs it, so a paragraph pair always lands on a true
facing left/right spread regardless of translation length — verified
end-to-end in this repo's test run (see `bilingual/typeset.py`'s docstring).
The known limitation: pairing is per-paragraph, not per-line, so an
unusually long paragraph can still spill onto a second page for that pair
before the next pair resumes on the correct sides.

## Fonts

Only SIL Open Font License (OFL) Arabic fonts are used — Amiri (body serif)
and Cairo (headings), fetched by `scripts/fetch_fonts.py` from the
`google/fonts` repository. Fonts aren't committed to git (binary, versioned
upstream); CI fetches them fresh (cached) on every run. English text in the
bilingual edition and the EPUB falls back to system/reader default serif
fonts — no separate Latin font is bundled.

## Weekly automation

`.github/workflows/weekly-book-factory.yml` runs every Monday (or via
manual `workflow_dispatch`, optionally with a specific `book_id`):

1. Installs system + Python deps, fetches fonts (cached).
2. Runs `scripts.run_pipeline` for the next queued book (needs the
   `ANTHROPIC_API_KEY` repository secret) through `generated -> qa_passed ->
   packaged`. A QA or build failure fails the job here, before any release
   is created.
3. Creates a **draft** GitHub Release tagged `book-<id>-<run_number>` with
   the package zip, metadata JSON, and the upload checklist CSV attached —
   review before uploading to KDP.
4. Only after the release is created does it flip the book's status to
   `published` and commit that plus the book's `metadata.json`/
   `manifest.json`/`package_manifest.json` back to `books.yaml`'s branch.

## Content & licensing notes

- `classics/` and `bilingual/` only ingest texts you configure via
  `source.url` — verify the source is genuinely public domain before
  queuing it. The pipeline never republishes the source text verbatim
  without also adding original editorial material (introduction,
  annotations, glossary, and for bilingual, a translation + translator's
  preface); it does not claim copyright over the underlying classical text
  itself.
- Generated introductions/annotations/glossaries/translations are original
  work produced by the Claude API from the source text's content, not
  copies of any third-party secondary source.
- The barcode area left blank on the back cover is filled in automatically
  by KDP during upload — do not draw anything there.
