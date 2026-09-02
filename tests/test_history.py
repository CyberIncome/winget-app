from __future__ import annotations

import json

import pytest

from src.logic import history


def _use_history_file(monkeypatch, path):
    monkeypatch.setattr(history, "HISTORY_FILE", path)


def test_history_is_bounded_to_recent_500_events(tmp_path, monkeypatch):
    path = tmp_path / "activity-history.jsonl"
    _use_history_file(monkeypatch, path)

    for index in range(510):
        history.record_event("scan", {"index": index})

    events = history.load_history(1000)
    assert len(events) == 500
    assert events[0]["data"]["index"] == 10
    assert events[-1]["data"]["index"] == 509


def test_history_skips_corrupt_or_oversized_records(tmp_path, monkeypatch):
    path = tmp_path / "activity-history.jsonl"
    _use_history_file(monkeypatch, path)
    path.write_bytes(
        b'{"type":"ok","data":{}}\n'
        + b"not-json\n"
        + (b"x" * (256 * 1024 + 1))
        + b"\n"
        + b'{"type":"also-ok","data":{}}\n'
    )

    events = history.load_history(10)
    assert [event["type"] for event in events] == ["ok", "also-ok"]


def test_history_clear_returns_removed_count(tmp_path, monkeypatch):
    path = tmp_path / "activity-history.jsonl"
    _use_history_file(monkeypatch, path)
    history.record_event("one")
    history.record_event("two")

    assert history.clear_history() == 2
    assert history.load_history() == []
    assert not path.exists()


def test_record_event_rejects_empty_type_and_sanitizes_payload(tmp_path, monkeypatch):
    path = tmp_path / "activity-history.jsonl"
    _use_history_file(monkeypatch, path)

    with pytest.raises(ValueError):
        history.record_event("   ")

    event = history.record_event(
        "example",
        {
            "long": "x" * 5000,
            "object": object(),
        },
    )
    assert len(event["data"]["long"]) == 4000
    assert isinstance(event["data"]["object"], str)


def test_snapshot_export_is_json_atomic_and_non_secret_by_contract(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        history,
        "get_build_info",
        lambda: {"version": "1.2.3", "commit": "a" * 40},
    )
    destination = tmp_path / "dashboard-snapshot"
    result = history.export_dashboard_snapshot(
        destination,
        updates=[{"Name": "Example", "Available": "2.0"}],
        inventory=[{"Name": "Example", "Version": "1.0"}],
        metadata={"ignored_updates": 2},
    )

    assert result.suffix == ".json"
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["schema"] == 1
    assert payload["application"]["version"] == "1.2.3"
    assert payload["updates"][0]["Available"] == "2.0"
    assert payload["inventory"][0]["Version"] == "1.0"
    assert payload["metadata"]["ignored_updates"] == 2
    assert not list(tmp_path.glob("*.tmp.*"))
