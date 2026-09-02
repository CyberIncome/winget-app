from __future__ import annotations

import pytest

from src.logic.app_release import check_latest_release, compare_semver, parse_semver
from src.logic.update_batch import BatchResultTracker
from src.logic.update_policy import (
    filter_ignored_updates,
    normalize_ignored_updates,
    package_identity,
)


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("1.0.0", "1.0.0", 0),
        ("1.0.1", "1.0.0", 1),
        ("1.0.0", "1.0.1", -1),
        ("1.0.0", "1.0.0-rc.1", 1),
        ("1.0.0-rc.2", "1.0.0-rc.10", -1),
        ("1.0.0-alpha", "1.0.0-beta", -1),
        ("1.0.0+build.2", "1.0.0+build.1", 0),
        ("1.0.0+01", "1.0.0+02", 0),
    ],
)
def test_semver_precedence(left, right, expected):
    assert compare_semver(left, right) == expected


@pytest.mark.parametrize(
    "value",
    [
        "v1.0.0",
        "1.0",
        "01.0.0",
        "1.0.0-01",
        "1.0.0-alpha..1",
        "1.0.0+foo..bar",
        "1.0.0+",
        "",
    ],
)
def test_semver_rejects_invalid(value):
    with pytest.raises(ValueError):
        parse_semver(value)


class _Response:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_release_check_picks_installer_and_reports_update():
    def getter(url, **kwargs):
        assert url.endswith("/releases/latest")
        assert kwargs["max_bytes"] == 512 * 1024
        assert "Authorization" not in kwargs["headers"]
        return _Response(
            200,
            {
                "tag_name": "v1.2.0",
                "html_url": "https://github.com/CyberIncome/winget-app/releases/tag/v1.2.0",
                "published_at": "2026-09-02T00:00:00Z",
                "body": "notes",
                "assets": [
                    {
                        "name": "WingetUniversalDashboard-Setup-x64.exe",
                        "browser_download_url": (
                            "https://github.com/CyberIncome/winget-app/releases/"
                            "download/v1.2.0/WingetUniversalDashboard-Setup-x64.exe"
                        ),
                    }
                ],
            },
        )

    result = check_latest_release("1.0.0", getter=getter)
    assert result["update_available"] is True
    assert result["latest_version"] == "1.2.0"
    assert result["installer_url"].endswith("WingetUniversalDashboard-Setup-x64.exe")


def test_release_check_handles_no_published_release():
    result = check_latest_release(
        "1.0.0", getter=lambda *_args, **_kwargs: _Response(404)
    )
    assert result["status"] == "no-release"
    assert result["update_available"] is False


def test_release_check_rejects_non_https_asset():
    result = check_latest_release(
        "1.0.0",
        getter=lambda *_args, **_kwargs: _Response(
            200,
            {
                "tag_name": "v1.1.0",
                "html_url": "https://github.com/CyberIncome/winget-app/releases/tag/v1.1.0",
                "assets": [
                    {
                        "name": "WingetUniversalDashboard-Setup-x64.exe",
                        "browser_download_url": "http://example.invalid/setup.exe",
                    }
                ],
            },
        ),
    )
    assert result["update_available"] is True
    assert result["installer_url"] is None


def test_release_check_rejects_malformed_tag():
    with pytest.raises(ValueError):
        check_latest_release(
            "1.0.0",
            getter=lambda *_args, **_kwargs: _Response(
                200,
                {
                    "tag_name": "v1.1.0+bad..metadata",
                    "html_url": "https://github.com/CyberIncome/winget-app/releases",
                },
            ),
        )


def test_ignored_updates_are_source_aware_and_normalized():
    winget = {
        "Name": "Example",
        "Id": "Vendor.Example",
        "Source": "winget",
    }
    private = {
        "Name": "Example",
        "Id": "Vendor.Example",
        "Source": "private",
    }
    identity = package_identity(winget)
    assert identity == "id:vendor.example|source:winget"
    ignored = normalize_ignored_updates([identity.upper(), identity, 7, "junk"])
    assert ignored == [identity]
    kept, removed = filter_ignored_updates([winget, private], ignored)
    assert kept == [private]
    assert removed == 1


def test_batch_tracker_counts_retry_only_when_terminal_state_recorded():
    refs = [
        {"value": "A.App", "match_by": "id", "source": "winget"},
        {"value": "B.App", "match_by": "id", "source": "winget"},
    ]
    tracker = BatchResultTracker(refs)
    tracker.record_success(refs[0])
    tracker.record_failure(refs[1], "exit code 1")
    tracker.record_failure(refs[0], "late duplicate failure")
    summary = tracker.summary()
    assert summary["requested"] == 2
    assert summary["succeeded"] == 1
    assert summary["failed"] == 1
    assert summary["pending"] == 0
    assert summary["failures"][0]["reason"] == "exit code 1"


def test_batch_tracker_reports_unfinished_refs():
    ref = {"value": "A.App", "match_by": "id"}
    summary = BatchResultTracker([ref]).summary()
    assert summary["pending"] == 1
    assert summary["pending_refs"] == [ref]
