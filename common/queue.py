"""Read/write helpers for books.yaml — the book production queue.

Pipeline stages (status field): each book advances strictly in this order,
or drops to "failed" (with `notes` explaining why) at any stage:

    queued -> generated -> qa_passed -> packaged -> published

    queued      not yet processed
    generated   interior + cover PDFs (and ebook, if requested) produced
    qa_passed   automated QA checks (qa/run_qa.py) passed
    packaged    final per-format deliverables assembled in output/<id>/package/
    published   attached to a GitHub release
    failed      pipeline error at any stage; see `notes`
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = REPO_ROOT / "books.yaml"

STATUS_PIPELINE = ["queued", "generated", "qa_passed", "packaged", "published"]
VALID_STATUSES = set(STATUS_PIPELINE) | {"failed"}
VALID_TYPES = {"classic", "bilingual", "lowcontent"}
VALID_FORMATS = {"paperback", "hardcover", "ebook"}


class QueueError(RuntimeError):
    pass


def next_status(status: str) -> str:
    """The status a book advances to after successfully completing `status`'s stage."""
    if status not in STATUS_PIPELINE:
        raise QueueError(f"'{status}' has no next stage (not part of the pipeline)")
    idx = STATUS_PIPELINE.index(status)
    if idx == len(STATUS_PIPELINE) - 1:
        raise QueueError(f"'{status}' is already the terminal stage")
    return STATUS_PIPELINE[idx + 1]


def load_queue(path: Path = QUEUE_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        raise QueueError(f"Queue file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or []
    if not isinstance(data, list):
        raise QueueError("books.yaml must be a top-level list of book entries")
    for entry in data:
        _validate_entry(entry)
    return data


def save_queue(entries: list[dict[str, Any]], path: Path = QUEUE_PATH) -> None:
    header = (
        "# =============================================================================\n"
        "# Arabic KDP Publishing Factory — book queue\n"
        "# See BOOK_FACTORY.md for the full field reference.\n"
        "# =============================================================================\n"
    )
    with path.open("w", encoding="utf-8") as fh:
        fh.write(header)
        yaml.safe_dump(
            entries,
            fh,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )


def _validate_entry(entry: dict[str, Any]) -> None:
    for field in ("id", "type", "formats", "trim_size", "status"):
        if field not in entry:
            raise QueueError(f"Book entry missing required field '{field}': {entry}")
    if entry["type"] not in VALID_TYPES:
        raise QueueError(f"Book '{entry['id']}' has invalid type '{entry['type']}'")
    if entry["status"] not in VALID_STATUSES:
        raise QueueError(f"Book '{entry['id']}' has invalid status '{entry['status']}'")
    formats = entry["formats"]
    if not isinstance(formats, list) or not formats:
        raise QueueError(f"Book '{entry['id']}' must have a non-empty 'formats' list")
    unknown = set(formats) - VALID_FORMATS
    if unknown:
        raise QueueError(f"Book '{entry['id']}' has unknown formats {unknown}; valid: {VALID_FORMATS}")
    if entry["type"] == "lowcontent" and "ebook" in formats:
        raise QueueError(
            f"Book '{entry['id']}' is type=lowcontent — 'ebook' format is not supported "
            "(planners/workbooks are print-only)"
        )


def find_book(book_id: str, path: Path = QUEUE_PATH) -> Optional[dict[str, Any]]:
    for entry in load_queue(path):
        if entry["id"] == book_id:
            return entry
    return None


def next_queued_book(path: Path = QUEUE_PATH) -> Optional[dict[str, Any]]:
    for entry in load_queue(path):
        if entry["status"] == "queued":
            return entry
    return None


def update_status(
    book_id: str,
    status: str,
    path: Path = QUEUE_PATH,
    notes: Optional[str] = None,
) -> None:
    if status not in VALID_STATUSES:
        raise QueueError(f"Invalid status '{status}'")
    entries = load_queue(path)
    found = False
    for entry in entries:
        if entry["id"] == book_id:
            entry["status"] = status
            entry["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if notes is not None:
                entry["notes"] = notes
            found = True
            break
    if not found:
        raise QueueError(f"Book '{book_id}' not found in queue")
    save_queue(entries, path)
