# Arabic KDP Publishing Factory

An automated pipeline that turns a queue (`books.yaml`) into print-ready
Amazon KDP packages — interior PDF(s), full-wrap cover PDF(s) per binding,
an EPUB where requested, and listing metadata — for three product lines,
gated by an automated QA pass (including a Claude **vision** check on
rasterized pages) before anything is ever packaged.

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
`hardcover`, `ebook` (EPUB3 with RTL support — classics/bilingual only). A
weekly GitHub Action processes the next queued book through the full
pipeline and attaches the results to a (draft) GitHub Release; a monthly
Action emails/prints a digest.

## Pipeline stages

Every book in `books.yaml` advances through a fixed state machine
(`common/queue.py`), and **every stage is idempotent and resumable** — see
"Idempotency & resuming" below:

```
queued -> generated -> qa_passed -> packaged -> published
                  \
                   -> failed   (at the "generated" build step or the QA gate;
                                 see the book's `notes` field, and
                                 output/<id>/qa_report/ for a quarantine
                                 report, for why)
```

| Stage | What happens | Where |
|---|---|---|
| `queued` | Book is waiting to be processed. | — |
| `generated` | Interior content produced (ingest/clean/generate/translate/typeset), one cover PDF per print format, one EPUB if `ebook` is requested, and listing metadata. | `scripts/run_pipeline.py` → product-line `build.py` + `covers/` + `ebook/` + `metadata/` |
| `qa_passed` | Automated structural/content checks passed (PDF sizes match KDP geometry, spine width matches page count, word counts/glossary/paragraph-alignment sane, metadata complete) **and** the Claude vision QA pass on rasterized pages passed. Otherwise: **quarantined**, never packaged. | `qa/run_qa.py`, `qa/vision_qa.py` |
| `packaged` | Final per-format deliverables copied into `output/<id>/package/` and zipped. | `bookpack/package_book.py` |
| `published` | Attached to a GitHub Release. | `.github/workflows/factory.yml`, after the release is created |

## Directory layout

```
books.yaml              # the production queue (see schema below)
common/
  kdp_specs.py           # KDP trim sizes, margins/gutter, spine width, paperback + hardcover cover geometry
  queue.py                # books.yaml read/write/status-pipeline helpers (incl. updated_at timestamps)
  arabic_text.py           # Arabic normalization (alef unification, tatweel, punctuation) + chapter-splitting
classics/
  ingest.py                # download a public-domain source text (idempotent: skips if raw.txt exists)
  clean.py                  # normalize + split into chapters (idempotent: skips if chapters.json exists)
  generate.py                # Claude API: intro, chapter annotations, glossary (idempotent)
  typeset.py                  # Jinja2 + WeasyPrint -> print-ready RTL interior PDF
  build.py                     # orchestrates the four steps above
  templates/book.html.j2, book.css
bilingual/
  translate.py              # Claude API: translator's preface + paragraph-aligned English translation (idempotent)
  typeset.py                  # Jinja2 + WeasyPrint -> facing-page interior PDF (English left / Arabic right)
  build.py                      # ingest/clean/generate (reused from classics/) -> translate -> typeset
  templates/bilingual_book.html.j2, bilingual_book.css
lowcontent/
  common/svg_utils.py       # tiny SVG page builder (RTL Arabic helpers)
  common/pdf_render.py       # SVG pages -> merged PDF
  planners/generate_planner.py     # weekly/monthly planner generator
  workbooks/generate_workbook.py    # letter-tracing / vocabulary-grid workbook generator
covers/
  generate_cover.py         # full wrap (back|spine|front) cover; paperback (bleed) or hardcover (wrap+hinge);
                             # deterministic per-series branding band (series_accent_color())
ebook/
  generate_epub.py          # packages a classic/bilingual book's generated content as an EPUB3 (RTL-tagged)
qa/
  run_qa.py                  # automated QA gate: PDF geometry, spine width, content sanity, metadata
                              # completeness, + orchestrates vision QA; writes the quarantine report on failure
  vision_qa.py                # rasterizes 5 random interior pages + the cover (PyMuPDF), sends them to
                                # Claude API vision, blocking on any defect
bookpack/
  package_book.py            # assembles + zips the final per-format deliverables (NOT named "packaging" —
                              # that collides with the PyPI `packaging` library, a transitive dependency of
                              # several other requirements here; see the comment in scripts/run_pipeline.py)
keywords/
  scrape_amazon.py           # Amazon autocomplete + competitor-listing-title scraper (robots.txt-respecting,
                              # rate-limited); feeds metadata/generate_metadata.py real search-demand signal
metadata/
  generate_metadata.py      # Claude API: title, subtitle, 7 keywords, 2 categories, description, series line
  export_csv.py               # compiles every book into upload_checklist.csv, incl. AI-content disclosure reminder
scripts/
  fetch_fonts.py             # downloads OFL Arabic fonts into assets/fonts/
  run_pipeline.py             # end-to-end, resumable: next queued book -> generated -> qa_passed -> packaged
report.py                 # monthly digest: packaged/published, QA failures, queue depth — emails or prints
.github/workflows/factory.yml            # weekly: process next queued book end-to-end
.github/workflows/monthly-report.yml     # monthly: run report.py
```

## One-time setup checklist

1. **Install dependencies and system libraries** (see "Setup" below).
2. **Get an Anthropic API key** and add it as the `ANTHROPIC_API_KEY`
   repository secret (Settings → Secrets and variables → Actions). This is
   the only secret required for the weekly factory workflow to run at all.
3. *(Optional, keyword research)* If you have an Amazon marketplace ID for
   autocomplete-suggestion scraping (see "Keyword research" below), add it
   as the `AMAZON_MARKETPLACE_ID` secret. Without it, the pipeline still
   works — it falls back to competitor-listing-title scraping alone, and
   ultimately to Claude's own knowledge if scraping is unavailable.
4. *(Optional, monthly digest email)* Add `SMTP_HOST`, `SMTP_PORT`,
   `SMTP_USER`, `SMTP_PASSWORD`, `DIGEST_TO_EMAIL` (and optionally
   `DIGEST_FROM_EMAIL`) secrets. Without these, `report.py` just prints the
   digest to the workflow log instead of emailing it — nothing breaks.
5. **Replace every `PLACEHOLDER source URL`** in `books.yaml` with a URL you
   have personally verified points to a public-domain (or otherwise
   rights-clear) plain-text/HTML edition before queuing a `classic` or
   `bilingual` book for real. Do not run the pipeline against an unverified
   source.
6. **Run once locally** (`python -m scripts.run_pipeline --dry-run`, then
   without `--dry-run` for a real book) before relying on the scheduled
   workflow, so you catch any environment/config issue interactively rather
   than in an unattended CI run.
7. **Review the first few packaged books by hand** before assuming the
   pipeline needs no supervision — the QA gate (including vision QA) is not
   a substitute for a human proof pass on your first several titles.

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

(the GitHub Action installs these automatically.) PDF rasterization for
vision QA uses PyMuPDF, a pure pip install with no separate system
`poppler`/`pdftoppm` dependency.

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
  rendered page count, with a series branding band if `series` is set
- `<id>.epub` — if `ebook` is a requested format (classic/bilingual only)
- `metadata.json` — title/subtitle/7 keywords/2 categories/description/series_line
- `manifest.json` — paths + computed KDP numbers (page count, spine width per format)
- `qa_report/` — rasterized sample pages, the vision QA verdict, and (on
  failure) `qa_failure_report.md` — the quarantine report
- `package/` and `<id>-package.zip` — the final upload-ready bundle (only
  produced once QA passes)

If any stage fails, the book's `status` becomes `failed` with a `notes`
field explaining why (a QA check name + detail, or a Python traceback for a
build error), and it is **quarantined** — `qa_report/qa_failure_report.md`
lists every check with its pass/fail state, and the book is never packaged
or released. It is **not** silently left as `queued` or partially advanced.
`metadata/export_csv.py` (run automatically at the end of `run_pipeline`)
refreshes `output/upload_checklist.csv`, a one-row-per-book KDP upload
checklist across the whole queue.

Individual stages can also be run standalone — see `--help` on each module
(`classics/ingest.py`, `classics/clean.py`, `classics/generate.py`,
`classics/typeset.py`, `bilingual/translate.py`, `bilingual/typeset.py`,
`covers/generate_cover.py` (`--binding paperback|hardcover`),
`ebook/generate_epub.py`,
`lowcontent/planners/generate_planner.py`,
`lowcontent/workbooks/generate_workbook.py`,
`metadata/generate_metadata.py`, `qa/run_qa.py` (`--no-vision` to skip the
Claude vision pass for local iteration), `bookpack/package_book.py`,
`keywords/scrape_amazon.py`, `report.py`).

## Idempotency & resuming

Every stage is safe to re-run:

- **`scripts/run_pipeline.py`** dispatches on the book's *current* status
  rather than always starting from scratch: a book stuck at `generated`
  (e.g. the runner died mid-QA) resumes straight into QA; a book at
  `qa_passed` resumes straight into packaging; `packaged`/`published` are
  no-ops. A `failed` book is retried from the generate stage, but —
- **every Claude-API-calling sub-step is individually idempotent**:
  `classics/ingest.py`, `classics/clean.py`, `classics/generate.py`,
  `bilingual/translate.py`, and `metadata/generate_metadata.py` all check
  whether their output file already exists and skip the expensive work
  (network fetch or Claude call) if so — pass `force=True` to redo a step
  deliberately. This means retrying a `failed` book only re-pays for
  whatever actually didn't finish, not the whole pipeline.
- Cheap, deterministic steps (typesetting, cover generation, EPUB
  packaging) always re-run — there's no reason to cache those, and
  re-running them picks up any change to the already-generated content.

## `books.yaml` schema

See the commented header in `books.yaml` for the full field reference.
Summary:

| Field | Applies to | Notes |
|---|---|---|
| `id` | all | slug, used for `output/<id>/` and filenames |
| `type` | all | `classic` \| `bilingual` \| `lowcontent` |
| `title_ar` | all | working title (metadata generation may refine it) |
| `title_en` | bilingual | working English title for the running header; falls back to `title_ar` |
| `series` | all, optional | drives the cover's branding band (`covers/generate_cover.py`) and is grouped in the upload checklist CSV |
| `formats` | all | list of `paperback` \| `hardcover` \| `ebook`. `ebook` is invalid for `lowcontent` (validated at load time) |
| `trim_size` | all | key into `common/kdp_specs.TRIM_SIZES`, e.g. `"6x9"` |
| `paper_type` | all | `white` \| `cream` \| `color` — affects spine width |
| `cover_style` | all, optional | `classic` \| `modern` \| `warm` palette, default `classic` |
| `status` | all | `queued` \| `generated` \| `qa_passed` \| `packaged` \| `published` \| `failed` |
| `updated_at` | all, auto-set | ISO-8601 UTC timestamp, set by `common/queue.update_status` on every status change; used by `report.py` to scope the digest window |
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

## Series branding (`covers/generate_cover.py`)

When a book has `series` set, its front and back cover each get a
branding band whose color is `series_accent_color(series)` — a hash of the
series name, deterministic, not stored anywhere — so every book in a
series carries the same accent color regardless of which individual
`cover_style` palette each title picks, giving the series a shared visual
identity without maintaining a color lookup table by hand.

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

## Visual QA (`qa/vision_qa.py`)

Structural checks (page sizes, spine math, word counts) can't see whether
Arabic actually *renders* correctly. Before a book can reach `qa_passed`,
`qa/run_qa.py` rasterizes 5 random interior pages plus the front-wrap cover
(via PyMuPDF — no system `poppler` dependency) and sends them to the Claude
API's vision capability, asking it to check: connected Arabic letterforms
(no broken ligatures), correct RTL (and, on a bilingual spread, LTR) reading
flow, no missing-glyph ("tofu") boxes, clean margins/bleed, and aligned
annotations. This is a genuinely **blocking** check — any vision-QA error
(a transient API failure, a parse error, an explicit fail verdict) counts
as an overall QA failure and quarantines the book (fail-closed by design;
see `qa/vision_qa.py`'s docstring). Use `qa/run_qa.py --no-vision` to skip
this pass during local iteration when you don't want to spend API calls on
every retry.

## Keyword research (`keywords/scrape_amazon.py`)

`metadata/generate_metadata.py` grounds its title/subtitle/keyword
generation in real search-demand signal where available: Amazon
autocomplete suggestions (requires an `AMAZON_MARKETPLACE_ID` — Amazon's
suggestion endpoint takes a locale-specific marketplace ID that isn't safe
to hardcode as a guess; obtain your own once via browser devtools) and
competitor listing titles from the public search results page. Both
respect `robots.txt` (checked and cached per domain, fails closed — a
robots.txt fetch error means "don't scrape that domain") and apply a fixed
delay between requests. **Honesty note:** outbound network access to
`amazon.<tld>` was not available from the sandbox this pipeline was
originally built in, so this module's HTTP calls are unit-tested against
local mocks/fixtures here, not against live Amazon traffic — verify it
against the real site (Amazon's HTML/endpoint shapes drift over time)
before relying on it in production. If scraping fails for any reason
(network, robots.txt, parsing), it degrades gracefully to an empty result
set rather than breaking metadata generation — Claude falls back to its own
knowledge.

## AI-content disclosure

Amazon KDP requires disclosing AI-generated content in a title's Publishing
Details form at upload time. `metadata/export_csv.py` adds an
`ai_content_disclosure` column to the checklist reminding you what to
disclose per book type: for `classic`/`bilingual`, the introduction,
annotations, glossary (and translation/preface for bilingual) are
AI-generated — the classical source text itself is not; for `lowcontent`,
the interior has no AI-generated content at all (only the marketing
metadata was AI-assisted, which KDP's content disclosure does not cover).
This is a reminder, not an automated KDP form submission — you still fill
in the actual disclosure yourself during upload (see the walkthrough
below).

## Fonts

Only SIL Open Font License (OFL) Arabic fonts are used — Amiri (body serif)
and Cairo (headings), fetched by `scripts/fetch_fonts.py` from the
`google/fonts` repository. Fonts aren't committed to git (binary, versioned
upstream); CI fetches them fresh (cached) on every run. English text in the
bilingual edition and the EPUB falls back to system/reader default serif
fonts — no separate Latin font is bundled.

## Weekly automation (`.github/workflows/factory.yml`)

Runs every Monday (or via manual `workflow_dispatch`, optionally with a
specific `book_id`):

1. Installs system + Python deps, fetches fonts (cached).
2. Runs `scripts.run_pipeline` for the next queued book (needs the
   `ANTHROPIC_API_KEY` repository secret, and optionally
   `AMAZON_MARKETPLACE_ID`) through `generated -> qa_passed -> packaged`.
3. **Always** (success or failure) commits the resulting `books.yaml`
   status change plus that book's `metadata.json`/`manifest.json`/
   `qa_report/` back to the branch — this is what actually persists a QA
   quarantine report to the repo instead of losing it when the runner is
   torn down. A QA/build failure correctly fails the job (red — a human
   needs to look at the quarantine report) even though the commit step
   still runs.
4. Only on success: creates a **draft** GitHub Release tagged
   `book-<id>-<run_number>` with the package zip, metadata JSON, and the
   upload checklist CSV attached, then flips the book's status to
   `published` and commits that.
5. Always uploads `output/` + `books.yaml` as a workflow artifact (30-day
   retention) — the fallback way to retrieve a quarantine report or
   rasterized QA sample pages without digging through commits.

## Monthly digest (`.github/workflows/monthly-report.yml`, `report.py`)

Runs on the 1st of every month: reports queue depth, books
packaged/published and QA failures in the last 30 days (via each book's
`updated_at` timestamp), and any book stuck mid-pipeline
(`generated`/`qa_passed` with no recent movement). Emails the digest via
SMTP if `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/
`DIGEST_TO_EMAIL` secrets are set; otherwise prints it to the workflow log
— safe default, nothing breaks without mail configured.

## KDP upload walkthrough

The pipeline gets you to a QA-passed `package/<id>-package.zip` — you still
do the actual KDP upload by hand (Amazon doesn't offer a publish API):

1. Download the release's `*-package.zip` (or pull it from
   `output/<id>/package/` if running locally) and unzip it. You'll find:
   `*-interior.pdf`, one `*-cover-<format>.pdf` per print format
   requested, `*.epub` if `ebook` was requested, and `metadata.json`.
2. Open `output/upload_checklist.csv` and find the book's row — it has
   the title, subtitle, description, categories, all 7 keywords, and the
   `ai_content_disclosure` reminder text, pre-filled and ready to paste.
3. In KDP (`kdp.amazon.com`) → **Create → Paperback** (or **Hardcover**,
   or **Kindle eBook**) → **Details**: paste title/subtitle/series
   (`series` + the generated `series_line`)/author/description, select the
   **2 categories** from the CSV, paste all **7 keywords**, and — under
   the **AI Content** section — disclose per the CSV's
   `ai_content_disclosure` column.
4. **Content**: upload `*-interior.pdf` as the manuscript, then upload the
   matching `*-cover-paperback.pdf` or `*-cover-hardcover.pdf` for that
   format's cover — KDP overlays its own ISBN/price barcode onto the
   blank placeholder area on the back cover automatically; don't draw
   anything there yourself. For **Kindle eBook**, upload the `.epub`
   instead (KDP converts it; no separate cover PDF needed there — use
   KDP's cover tool or a still image if you want a matching Kindle cover).
   Use KDP's print previewer to spot-check the render before publishing
   even though the vision QA gate already passed it.
5. **Pricing**: set territory/pricing per format as usual (out of scope
   for this pipeline).
6. Repeat per format — `paperback`/`hardcover`/`ebook` are **separate KDP
   listings** you link together as one book with multiple formats in KDP's
   UI (or as a series, if `series` is set); the pipeline produces the
   files for each, but KDP's own multi-format linking is a manual step.
7. Publish (or save as draft for further review) — the pipeline's own
   `published` status only means "the GitHub Release exists," not "live on
   Amazon"; those are two different senses of "published" and only you
   control the second one.

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
