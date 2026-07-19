"""Keyword-research scraper: Amazon search-autocomplete suggestions and
competitor listing titles for an Arabic-language storefront, feeding
metadata/generate_metadata.py with real search-demand signal instead of
guessing keywords cold.

Honesty note: outbound network access to amazon.<tld> is blocked from this
development sandbox (proxy policy denies arbitrary domains), so the HTTP
calls in this module are NOT exercised against live Amazon traffic here —
only unit-tested against local fixtures/mocks (see the test invocation in
the PR notes). Amazon's HTML structure and any undocumented endpoints can
change without notice; treat the CSS selectors below as a starting point to
verify and adjust against the real site, not a guarantee.

Respects robots.txt (checked once per domain, cached) before every request,
and applies a fixed delay between requests (gentle rate limiting). Returns
empty results — never raises — on any network/robots/parsing failure, so a
scraping outage degrades metadata quality rather than breaking the pipeline.
"""

from __future__ import annotations

import time
import urllib.robotparser
from urllib.parse import quote
from urllib.request import urlopen, Request

import requests
from bs4 import BeautifulSoup

USER_AGENT = "arabic-kdp-book-factory-keyword-research/1.0 (+https://github.com/)"
REQUEST_DELAY_SECS = 2.0
REQUEST_TIMEOUT_SECS = 15
DEFAULT_DOMAIN = "www.amazon.ae"  # Arabic-language storefront; amazon.sa / amazon.eg also serve Arabic

_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}
_last_request_at: dict[str, float] = {}


def _robots_allowed(domain: str, path: str) -> bool:
    """Fetch (and cache) robots.txt for `domain` and check whether our user
    agent may fetch `path`. Fails closed: any error reading robots.txt means
    we do NOT scrape that domain."""
    if domain not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"https://{domain}/robots.txt")
        try:
            req = Request(f"https://{domain}/robots.txt", headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=REQUEST_TIMEOUT_SECS) as resp:
                rp.parse(resp.read().decode("utf-8", errors="replace").splitlines())
        except Exception:
            return False
        _robots_cache[domain] = rp
    return _robots_cache[domain].can_fetch(USER_AGENT, path)


def _gentle_get(domain: str, path: str, params: dict | None = None) -> requests.Response | None:
    if not _robots_allowed(domain, path):
        return None

    last = _last_request_at.get(domain, 0.0)
    wait = REQUEST_DELAY_SECS - (time.monotonic() - last)
    if wait > 0:
        time.sleep(wait)
    _last_request_at[domain] = time.monotonic()

    try:
        resp = requests.get(
            f"https://{domain}{path}",
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "ar"},
            timeout=REQUEST_TIMEOUT_SECS,
        )
        resp.raise_for_status()
        return resp
    except requests.RequestException:
        return None


def fetch_autocomplete_suggestions(query: str, mid: str, domain: str = DEFAULT_DOMAIN) -> list[str]:
    """Fetch search-autocomplete suggestions for `query`.

    `mid` is the storefront's marketplace ID, a value specific to each
    Amazon locale that isn't safe to hardcode as a guess here — obtain it
    once by inspecting the autocomplete network request in a browser on the
    target storefront (search box -> devtools -> Network -> filter
    "suggestions") and pass it in (e.g. via an environment variable). If not
    supplied, this function returns an empty list rather than guessing.
    """
    if not mid:
        return []
    path = "/api/2017/suggestions"
    resp = _gentle_get(
        f"completion.{domain}", path,
        params={"mid": mid, "alias": "aps", "prefix": query, "limit": 10},
    )
    if resp is None:
        return []
    try:
        data = resp.json()
        return [
            s["value"] for s in data.get("suggestions", [])
            if isinstance(s, dict) and s.get("value")
        ]
    except (ValueError, KeyError):
        return []


def fetch_competitor_titles(query: str, domain: str = DEFAULT_DOMAIN, max_results: int = 10) -> list[str]:
    """Fetch the titles of the top public search results for `query` on the
    given Amazon storefront's search page (no private API needed)."""
    resp = _gentle_get(f"www.{domain.removeprefix('www.')}", "/s", params={"k": query})
    if resp is None:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    titles: list[str] = []
    # Amazon's search-result markup changes over time; try the current
    # common selectors, falling back to a broader heuristic.
    for el in soup.select("div[data-component-type='s-search-result'] h2 span"):
        text = el.get_text(strip=True)
        if text:
            titles.append(text)
        if len(titles) >= max_results:
            break
    if not titles:
        for el in soup.select("h2 a span"):
            text = el.get_text(strip=True)
            if text:
                titles.append(text)
            if len(titles) >= max_results:
                break
    return titles


def get_keyword_candidates(query: str, mid: str | None = None, domain: str = DEFAULT_DOMAIN) -> dict:
    """Best-effort combined keyword-research signal for `query`. Never
    raises — returns empty lists on any scraping failure so a metadata
    generation run degrades gracefully instead of breaking."""
    try:
        autocomplete = fetch_autocomplete_suggestions(query, mid or "", domain) if mid else []
    except Exception:  # noqa: BLE001
        autocomplete = []
    try:
        competitor_titles = fetch_competitor_titles(query, domain)
    except Exception:  # noqa: BLE001
        competitor_titles = []
    return {"query": query, "autocomplete": autocomplete, "competitor_titles": competitor_titles}


def main() -> None:
    import argparse
    import json
    import os

    parser = argparse.ArgumentParser(description="Fetch Amazon keyword-research candidates for a query")
    parser.add_argument("--query", required=True)
    parser.add_argument("--domain", default=DEFAULT_DOMAIN)
    parser.add_argument("--mid", default=os.environ.get("AMAZON_MARKETPLACE_ID", ""))
    args = parser.parse_args()

    candidates = get_keyword_candidates(args.query, mid=args.mid or None, domain=args.domain)
    print(json.dumps(candidates, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
