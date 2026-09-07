# egydir.com company scraper

Crawls the company/factory/importer/exporter listings on [egydir.com](https://www.egydir.com)
(an Egyptian business directory) and exports the results to `.xlsx` with:

| Column | Notes |
| --- | --- |
| Company Name | |
| Line of Business | parsed from the sector/activity field on the company's profile page |
| Location | parsed from the address/city field |
| Has Website | `Yes` / `No` |
| Website | the company's own site, if listed |
| Clients | best-effort only, see caveat below — blank unless `--fetch-clients` is passed and a website exists |
| Contact Number | phone number(s) from the profile page, `; `-separated if more than one |
| Source URL | the egydir.com profile page the row came from, for spot-checking |

## Quick start

```bash
pip install -r requirements.txt   # requests, beautifulsoup4, openpyxl

# 1. Sanity-check the parsing against the live site first (see "Selectors" below)
python -m scripts.egydir_scraper.scraper --dry-run

# 2. Full crawl of the "company" listings
python -m scripts.egydir_scraper.scraper --output companies.xlsx

# Also crawl factories/importers/exporters
python -m scripts.egydir_scraper.scraper --types company factory importer exporter -o companies.xlsx

# Best-effort client-name lookup on each company's own site (slow - one extra
# fetch per company, and often finds nothing; see caveat below)
python -m scripts.egydir_scraper.scraper --fetch-clients -o companies.xlsx
```

The crawl writes every company to `--checkpoint` (a `.jsonl` file, default
`scripts/egydir_scraper/output/egydir_checkpoint.jsonl`) as it goes, so:

- Interrupting with Ctrl-C still produces a valid `.xlsx` from whatever was
  collected so far.
- Re-run with `--resume` to continue a large crawl without re-fetching
  companies already in the checkpoint.
- `--export-only <checkpoint.jsonl>` rebuilds the `.xlsx` from a checkpoint
  with no network calls at all — useful after tweaking column formatting, or
  to combine/re-export a run.

Run `python -m scripts.egydir_scraper.scraper --help` for every flag
(`--sectors`, `--cities`, `--max-pages`, `--limit`, `--delay`, ...).

## Important: this was built without live access to egydir.com

The sandbox this tool was written in has network egress blocked for
`egydir.com`, so the parsing logic could **not** be tested against the
site's real HTML — only against synthetic markup built from the URL
patterns and page descriptions turned up via search (`/en/listings/company?
sector=<id>&page=<n>`, profile pages under `/en/<id>/<slug>/about`, etc.).
The crawl/pagination/checkpointing/Excel-export machinery is fully tested;
what's unverified is whether `parse_detail_page`'s label matching finds the
right fields in egydir.com's actual template.

**Before a full run**, run `--dry-run`: it fetches one listing page and one
company profile page, then prints exactly what was extracted. If a field
comes back empty that you can see on the real page, open that page's HTML,
find the label the site actually uses (e.g. it might say "التليفون" /
"العنوان" if the `/en/` pages still render Arabic labels for some fields, or
use icon-only rows with no text label at all), and extend the relevant tuple
near the top of `scraper.py`:

```python
LOCATION_LABELS = ("address", "location", "city", "governorate", "area", "district")
PHONE_LABELS = ("phone", "tel", "telephone", "mobile", "fax", "contact")
WEBSITE_LABELS = ("website", "web site", "web", "url", "site")
SECTOR_LABELS = ("sector", "activity", "industry", "business", "category", "line of business")
```

If the site uses icon+text rows with no colon-separated label at all,
`_extract_label_value_pairs` won't catch them — the phone number will still
usually be found via the `tel:` link fallback (very common) or the regex
fallback over the page text, and the website via the "any external, non-social
link" fallback, but location/sector may need a small selector added once you
can see the real markup (e.g. `soup.select_one(".company-address")`).

## The "Clients" column is inherently best-effort

There is no directory of client names on egydir.com itself — the ask was to
visit each company's *own* external website and pull out who their clients
are. Every company site is built differently (different CMS, different
wording, some have no clients page at all), so `find_client_names()` is a
heuristic:

1. Fetch the company's homepage.
2. Look for a nav link whose text matches `client|customer|partner|portfolio`
   (or the Arabic عملاء/شركاء) and fetch that page instead.
3. Inside whatever page it lands on, pull image `alt` text and short
   heading/list text from any container whose class/id mentions
   client/customer/partner (client logos are very often marked up this way).

This will miss plenty of real client lists (JS-rendered logo carousels, PDF
brochures, clients named only in body prose) and will occasionally pick up
noise. Treat the column as a lead to verify, not a ground truth. It's off by
default (`--fetch-clients` to enable) because it roughly doubles request
volume and hits arbitrary third-party sites.

## Etiquette / legal

- The crawler checks `robots.txt` on every host it touches (egydir.com and,
  with `--fetch-clients`, each company's own site) via `urllib.robotparser`
  and skips disallowed URLs rather than fetching them anyway.
- Requests go through a single `requests.Session` with a `--delay` (default
  1.5s + jitter) between them and a descriptive `User-Agent` — it does not
  parallelize or attempt to evade rate limiting.
- You are responsible for checking egydir.com's Terms of Service and applicable
  law (e.g. data protection rules for the contact details you export) before
  running a large crawl or using the output commercially.
