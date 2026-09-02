"""Bounded local activity history and support snapshot export."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import uuid

from src.app_info import get_build_info
from src.logic.config import CONFIG_DIR


HISTORY_FILE = Path(CONFIG_DIR) / "activity-history.jsonl"
MAX_HISTORY_ENTRIES = 500
MAX_HISTORY_READ_BYTES = 2 * 1024 * 1024
MAX_EVENT_BYTES = 128 * 1024
MAX_HISTORY_COLLECTION_ITEMS = 200
MAX_SNAPSHOT_COLLECTION_ITEMS = 10_000
_LOCK = threading.RLock()


def _safe_value(value, *, depth: int = 0, collection_limit: int = 200):
    if depth > 6:
        return "<depth-limit>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:4000]
    if isinstance(value, dict):
        result = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= collection_limit:
                break
            result[str(key)[:200]] = _safe_value(
                item,
                depth=depth + 1,
                collection_limit=collection_limit,
            )
        return result
    if isinstance(value, (list, tuple, set)):
        return [
            _safe_value(
                item,
                depth=depth + 1,
                collection_limit=collection_limit,
            )
            for item in list(value)[:collection_limit]
        ]
    return str(value)[:4000]


def _serialize_event(event: dict) -> str:
    encoded = json.dumps(event, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) <= MAX_EVENT_BYTES:
        return encoded
    fallback = dict(event)
    fallback["data"] = {
        "truncated": True,
        "reason": "event payload exceeded history safety limit",
    }
    encoded = json.dumps(fallback, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_EVENT_BYTES:
        raise ValueError("history event metadata exceeded safety limit")
    return encoded


def _read_recent_events() -> list[dict]:
    if not HISTORY_FILE.is_file():
        return []
    recent: deque[dict] = deque(maxlen=MAX_HISTORY_ENTRIES)
    try:
        with HISTORY_FILE.open("rb") as handle:
            size = HISTORY_FILE.stat().st_size
            if size > MAX_HISTORY_READ_BYTES:
                handle.seek(size - MAX_HISTORY_READ_BYTES)
                handle.readline()  # discard a potentially partial first record
            for raw_line in handle:
                if len(raw_line) > MAX_EVENT_BYTES:
                    continue
                try:
                    payload = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(payload, dict):
                    recent.append(payload)
    except OSError:
        return []
    return list(recent)


def _rewrite_events(events: list[dict]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = HISTORY_FILE.with_name(
        f"{HISTORY_FILE.name}.tmp.{os.getpid()}.{threading.get_ident()}"
    )
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            for event in events[-MAX_HISTORY_ENTRIES:]:
                handle.write(_serialize_event(event) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, HISTORY_FILE)
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass


def record_event(event_type: str, data: dict | None = None) -> dict:
    """Persist one bounded semantic event and return its sanitized payload."""
    event_name = str(event_type or "").strip()[:80]
    if not event_name:
        raise ValueError("event_type cannot be empty")
    event = {
        "id": uuid.uuid4().hex,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": event_name,
        "data": _safe_value(
            data or {},
            collection_limit=MAX_HISTORY_COLLECTION_ITEMS,
        ),
    }
    # Normalize oversize events before they reach disk so the writer never
    # creates a record that the bounded reader must later discard.
    normalized = json.loads(_serialize_event(event))
    with _LOCK:
        events = _read_recent_events()
        events.append(normalized)
        _rewrite_events(events)
    return normalized


def load_history(limit: int = 50) -> list[dict]:
    limit = max(0, min(int(limit), MAX_HISTORY_ENTRIES))
    if limit == 0:
        return []
    with _LOCK:
        return _read_recent_events()[-limit:]


def clear_history() -> int:
    with _LOCK:
        count = len(_read_recent_events())
        try:
            HISTORY_FILE.unlink()
        except FileNotFoundError:
            pass
        return count


def export_dashboard_snapshot(
    destination: Path,
    *,
    updates: list[dict],
    inventory: list[dict],
    metadata: dict | None = None,
) -> Path:
    """Atomically export a bounded JSON snapshot for inspection/support."""
    destination = Path(destination)
    if destination.suffix.lower() != ".json":
        destination = destination.with_suffix(".json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "application": get_build_info(),
        "metadata": _safe_value(
            metadata or {},
            collection_limit=MAX_HISTORY_COLLECTION_ITEMS,
        ),
        "updates": _safe_value(
            list(updates or [])[:MAX_SNAPSHOT_COLLECTION_ITEMS],
            collection_limit=MAX_SNAPSHOT_COLLECTION_ITEMS,
        ),
        "inventory": _safe_value(
            list(inventory or [])[:MAX_SNAPSHOT_COLLECTION_ITEMS],
            collection_limit=MAX_SNAPSHOT_COLLECTION_ITEMS,
        ),
    }
    temp = destination.with_name(
        f"{destination.name}.tmp.{os.getpid()}.{threading.get_ident()}"
    )
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, destination)
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass
    return destination
