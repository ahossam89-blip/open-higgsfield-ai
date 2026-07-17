# Arabic KDP Book Factory

An automated pipeline that turns a queue (`books.yaml`) into print-ready
Amazon KDP paperback packages — interior PDF, full-wrap cover PDF, and
listing metadata — for two kinds of Arabic books:

- **Classics** — public-domain Arabic texts re-published with an original
  Claude-generated introduction, chapter annotations, and glossary.
- **Low-content** — parametric planners and Arabic handwriting/practice
  workbooks, generated programmatically (no AI text, just layout).

A weekly GitHub Action processes the next queued book end-to-end and
attaches the results to a (draft) GitHub Release.

## Directory layout

```
books.yaml              # the production queue (see schema below)
common/
  kdp_specs.py           # KDP trim sizes, margins/gutter, spine width, cover geometry
  queue.py                # books.yaml read/write/status helpers
  arabic_text.py           # Arabic normalization + chapter-splitting
classics/
  ingest.py                # download a public-domain source text
  clean.py                  # normalize + split into chapters
  generate.py                # Claude API: intro, chapter annotations, glossary
  typeset.py                  # Jinja2 + WeasyPrint -> print-ready interior PDF
  build.py                     # orchestrates the four steps above
  templates/book.html.j2, book.css
lowcontent/
  common/svg_utils.py       # tiny SVG page builder (RTL Arabic helpers)
  common/pdf_render.py       # SVG pages -> merged PDF
  planners/generate_planner.py     # weekly/monthly planner generator
  workbooks/generate_workbook.py    # letter-tracing workbook generator
covers/
  generate_cover.py         # full wrap (back|spine|front) cover from page count
metadata/
  generate_metadata.py      # Claude API: title, subtitle, 7 keywords, categories, description
  export_csv.py               # compiles every book into upload_checklist.csv
scripts/
  fetch_fonts.py             # downloads OFL Arabic fonts into assets/fonts/
  run_pipeline.py             # end-to-end: next queued book -> interior + cover + metadata
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

Process the next `status: queued` book in `books.yaml` (classic or
low-content — the orchestrator dispatches automatically):

```bash
python -m scripts.run_pipeline
```

Process a specific book, or preview what would run:

```bash
python -m scripts.run_pipeline --id kalila-wa-dimna
python -m scripts.run_pipeline --dry-run
```

This writes `output/<book_id>/`:
- `<id>-interior.pdf` — the manuscript PDF (KDP margins, trim size)
- `<id>-cover.pdf` — the full-wrap cover PDF (spine width computed from the
  actual rendered page count)
- `metadata.json` — title/subtitle/7 keywords/categories/description
- `manifest.json` — paths + computed KDP numbers (page count, spine width)

and flips the book's `status` in `books.yaml` to `published` (or `failed`
with a note, on error). `metadata/export_csv.py` (run automatically at the
end of `run_pipeline`) refreshes `output/upload_checklist.csv`, a
one-row-per-book KDP upload checklist across the whole queue.

Individual stages can also be run standalone — see `--help` on each module
(`classics/ingest.py`, `classics/clean.py`, `classics/generate.py`,
`classics/typeset.py`, `covers/generate_cover.py`,
`lowcontent/planners/generate_planner.py`,
`lowcontent/workbooks/generate_workbook.py`,
`metadata/generate_metadata.py`).

## `books.yaml` schema

See the commented header in `books.yaml` for the full field reference.
Summary:

| Field | Applies to | Notes |
|---|---|---|
| `id` | all | slug, used for `output/<id>/` and filenames |
| `type` | all | `classic` \| `low-content` |
| `title_ar` | all | working title (metadata generation may refine it) |
| `trim_size` | all | key into `common/kdp_specs.TRIM_SIZES`, e.g. `"6x9"` |
| `paper_type` | all | `white` \| `cream` \| `color` — affects spine width |
| `status` | all | `queued` \| `in_progress` \| `published` \| `failed` |
| `source.url/format/encoding` | classic | source text to ingest |
| `author_ar`, `chapters` | classic | colophon author; `"auto"` or a regex heading pattern |
| `generator` | low-content | `planner` \| `workbook` |
| `spec` | low-content | generator-specific params — see the generator module docstring |

## KDP specifics (`common/kdp_specs.py`)

- **Trim sizes**: the full KDP paperback catalogue (5x8 through 8.5x11, A4).
- **Gutter/margins**: KDP's no-bleed interior margin table by page count
  (0.375in–0.875in inside margin), plus configurable top/bottom/outside.
  `classics/typeset.py` renders the interior twice: once to measure the
  actual page count, once more with the correct KDP margins for that count.
- **Spine width**: `page_count * factor`, factor per paper stock
  (white/cream/color), per KDP's published constants.
- **Cover geometry**: `compute_cover_layout()` returns the full bleed sheet
  size and the back/spine/front panel boundaries. KDP's flat cover file is
  always laid out back-cover-left, spine-center, front-cover-right — that's
  a fixed print-production convention independent of the interior's RTL
  reading direction, so it applies the same way here.
- Spine text is only placed if `page_count >= 100`, per KDP's own rule.

## Fonts

Only SIL Open Font License (OFL) Arabic fonts are used — Amiri (body serif)
and Cairo (headings), fetched by `scripts/fetch_fonts.py` from the
`google/fonts` repository. Fonts aren't committed to git (binary, versioned
upstream); CI fetches them fresh (cached) on every run.

## Weekly automation

`.github/workflows/weekly-book-factory.yml` runs every Monday (or via
manual `workflow_dispatch`, optionally with a specific `book_id`):

1. Installs system + Python deps, fetches fonts (cached).
2. Runs `scripts.run_pipeline` for the next queued book (needs the
   `ANTHROPIC_API_KEY` repository secret).
3. Commits the `books.yaml` status flip + that book's `metadata.json`/`manifest.json`.
4. Creates a **draft** GitHub Release tagged `book-<id>-<run_number>` with
   the interior PDF, cover PDF, metadata JSON, and the upload checklist CSV
   attached — review before uploading to KDP.

## Content & licensing notes

- `classics/` only ingests texts you configure via `source.url` — verify
  the source is genuinely public domain before queuing it. The pipeline
  never republishes the source text verbatim without also adding original
  editorial material (introduction, annotations, glossary); it does not
  claim copyright over the underlying classical text itself.
- Generated introductions/annotations/glossaries are original commentary
  produced by the Claude API from the source text's content, not copies of
  any third-party secondary source.
- The barcode area left blank on the back cover is filled in automatically
  by KDP during upload — do not draw anything there.
