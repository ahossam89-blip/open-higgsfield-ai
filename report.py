"""Monthly digest: books packaged, QA failures, and queue depth, emailed
via SMTP using GitHub Secrets — or printed to stdout if no SMTP secrets are
configured (local/dry-run use, and safe default for forks without mail set up).

Uses each book's `updated_at` timestamp (set by common/queue.update_status
on every status change) to scope "packaged"/"failed" to the lookback
window, rather than reporting the whole queue's history every time.

Environment (all optional — missing SMTP config means "print, don't send"):
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD   mail server credentials
    DIGEST_FROM_EMAIL                                 From: address (default SMTP_USER)
    DIGEST_TO_EMAIL                                    To: address(es), comma-separated
"""

from __future__ import annotations

import argparse
import os
import smtplib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from common.queue import load_queue

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_LOOKBACK_DAYS = 30


def _parse_updated_at(book: dict) -> datetime | None:
    raw = book.get("updated_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _within_lookback(book: dict, since: datetime) -> bool:
    updated = _parse_updated_at(book)
    return updated is not None and updated >= since


@dataclass
class Digest:
    period_days: int
    queue_depth: int
    packaged: list[dict] = field(default_factory=list)
    published: list[dict] = field(default_factory=list)
    qa_failures: list[dict] = field(default_factory=list)
    stuck_in_progress: list[dict] = field(default_factory=list)
    total_books: int = 0

    def subject(self) -> str:
        return (
            f"Arabic KDP Publishing Factory — monthly digest: "
            f"{len(self.packaged) + len(self.published)} packaged, "
            f"{len(self.qa_failures)} QA failures, {self.queue_depth} queued"
        )

    def text_body(self) -> str:
        lines = [
            "Arabic KDP Publishing Factory — monthly digest",
            f"Period: last {self.period_days} days",
            "",
            f"Queue depth (status=queued): {self.queue_depth}",
            f"Total books tracked: {self.total_books}",
            "",
            f"Packaged/published this period: {len(self.packaged) + len(self.published)}",
        ]
        for b in self.published + self.packaged:
            lines.append(f"  - [{b['status']}] {b['id']} — {b.get('title_ar', '')} ({b.get('series') or 'no series'})")

        lines += ["", f"QA failures this period: {len(self.qa_failures)}"]
        for b in self.qa_failures:
            note = (b.get("notes") or "").strip()
            lines.append(f"  - {b['id']} — {b.get('title_ar', '')}")
            if note:
                lines.append(f"      {note[:300]}")

        if self.stuck_in_progress:
            lines += ["", f"Stuck mid-pipeline (generated/qa_passed, no recent movement): {len(self.stuck_in_progress)}"]
            for b in self.stuck_in_progress:
                lines.append(f"  - [{b['status']}] {b['id']} — {b.get('title_ar', '')}")

        lines += ["", "-- Arabic KDP Publishing Factory (automated)"]
        return "\n".join(lines)


def build_digest(lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> Digest:
    books = load_queue()
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    digest = Digest(
        period_days=lookback_days,
        queue_depth=sum(1 for b in books if b["status"] == "queued"),
        total_books=len(books),
    )
    for b in books:
        if b["status"] == "packaged" and _within_lookback(b, since):
            digest.packaged.append(b)
        elif b["status"] == "published" and _within_lookback(b, since):
            digest.published.append(b)
        elif b["status"] == "failed" and _within_lookback(b, since):
            digest.qa_failures.append(b)
        elif b["status"] in ("generated", "qa_passed"):
            digest.stuck_in_progress.append(b)
    return digest


def send_digest(digest: Digest) -> bool:
    """Sends the digest via SMTP if all required env vars are set; returns
    True if actually sent, False if it just printed to stdout instead."""
    host = os.environ.get("SMTP_HOST")
    port = os.environ.get("SMTP_PORT")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    to_addr = os.environ.get("DIGEST_TO_EMAIL")
    from_addr = os.environ.get("DIGEST_FROM_EMAIL", user)

    if not all([host, port, user, password, to_addr]):
        print("(SMTP not fully configured — printing digest instead of emailing)\n")
        print(digest.text_body())
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = digest.subject()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(digest.text_body(), "plain", "utf-8"))

    with smtplib.SMTP(host, int(port)) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(from_addr, [a.strip() for a in to_addr.split(",")], msg.as_string())

    print(f"Digest emailed to {to_addr}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and send/print the monthly factory digest")
    parser.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS, help="Lookback window in days")
    parser.add_argument("--dry-run", action="store_true", help="Print the digest, never send email")
    args = parser.parse_args()

    digest = build_digest(args.days)
    if args.dry_run:
        print(digest.text_body())
    else:
        send_digest(digest)


if __name__ == "__main__":
    main()
