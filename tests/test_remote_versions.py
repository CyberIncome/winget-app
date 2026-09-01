"""Regression coverage for the hardened remote-version detector."""

from __future__ import annotations

import os

import pytest

if os.name != "nt":
    pytest.skip(
        "remote-version detector imports Windows inventory helpers",
        allow_module_level=True,
    )

import src.logic.remote_versions as remote_versions


class FakeResponse:
    def __init__(
        self,
        status_code=200,
        *,
        payload=None,
        text="",
        url="https://example.com/",
        headers=None,
    ):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.url = url
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeConfig:
    github_pat = "secret"


def test_github_repo_parts_requires_actual_github_host():
    assert remote_versions._github_repo_parts(
        "https://github.com/owner/repo/releases"
    ) == ("owner", "repo")
    assert (
        remote_versions._github_repo_parts(
            "https://example.com/?next=github.com/owner/repo"
        )
        is None
    )


def test_github_api_version_uses_hardened_transport(monkeypatch):
    calls = []

    def fake_safe_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(
            payload={"tag_name": "v2.0.0"},
            url=url,
        )

    monkeypatch.setattr(remote_versions, "ConfigManager", lambda: FakeConfig())
    monkeypatch.setattr(remote_versions, "safe_get", fake_safe_get)

    assert (
        remote_versions.check_remote_version(
            "https://github.com/owner/repo/releases",
            "1.0.0",
        )
        == "2.0.0"
    )
    assert calls[0][0] == (
        "https://api.github.com/repos/owner/repo/releases/latest"
    )
    assert calls[0][1]["headers"]["Authorization"] == "Bearer secret"


def test_github_rate_limit_falls_back_to_latest_tag(monkeypatch):
    responses = [
        FakeResponse(
            403,
            headers={"X-RateLimit-Remaining": "0"},
        ),
        FakeResponse(
            200,
            url="https://github.com/owner/repo/releases/tag/v3.1.0",
        ),
    ]

    monkeypatch.setattr(remote_versions, "ConfigManager", lambda: FakeConfig())
    monkeypatch.setattr(
        remote_versions,
        "safe_get",
        lambda *_args, **_kwargs: responses.pop(0),
    )

    assert (
        remote_versions.check_remote_version(
            "https://github.com/owner/repo/releases",
            "3.0.0",
        )
        == "3.1.0"
    )


def test_generic_release_page_chooses_highest_newer_version(monkeypatch):
    monkeypatch.setattr(
        remote_versions,
        "safe_get",
        lambda *_args, **_kwargs: FakeResponse(
            text=(
                "Historical releases: v4.1.1, v4.3.0, v4.2.9, "
                "current v4.10.0"
            ),
        ),
    )

    assert (
        remote_versions.check_remote_version(
            "https://vendor.example/releases",
            "4.1.0",
        )
        == "4.10.0"
    )


def test_unsafe_url_is_rejected_before_transport(monkeypatch):
    called = False

    def fake_safe_get(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("transport must not be called")

    monkeypatch.setattr(remote_versions, "safe_get", fake_safe_get)

    assert (
        remote_versions.check_remote_version(
            "https://user:password@example.com/releases",
            "1.0",
        )
        is None
    )
    assert called is False


def test_remote_versions_does_not_monkey_patch_legacy_parser():
    source = open(
        remote_versions.__file__,
        "r",
        encoding="utf-8",
    ).read()
    assert "parser._safe_get" not in source
    assert "parser._is_safe_url" not in source
