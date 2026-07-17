"""Read/write helpers for books.yaml — the book production queue."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = REPO_ROOT / "books.yaml"

VALID_STATUSES = {"queued", "in_progress", "published", "failed"}
VALID_TYPES = {"classic", "low-content"}


class QueueError(RuntimeError):
    pass


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
        "# Arabic KDP Book Factory — book queue\n"
        "# See git history / README for the full field reference.\n"
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
    for field in ("id", "type", "trim_size", "status"):
        if field not in entry:
            raise QueueError(f"Book entry missing required field '{field}': {entry}")
    if entry["type"] not in VALID_TYPES:
        raise QueueError(f"Book '{entry['id']}' has invalid type '{entry['type']}'")
    if entry["status"] not in VALID_STATUSES:
        raise QueueError(f"Book '{entry['id']}' has invalid status '{entry['status']}'")


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
            if notes is not None:
                entry["notes"] = notes
            found = True
            break
    if not found:
        raise QueueError(f"Book '{book_id}' not found in queue")
    save_queue(entries, path)
