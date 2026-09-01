import pytest

from src.logic.parser import (
    _is_safe_url,
    check_remote_version,
    is_valid_version,
    is_version_newer,
    parse_version_tuple,
    parse_winget_upgrade,
)
from src.logic.upgrade_parser import WingetParseError


class FakeResponse:
    def __init__(self, status_code, url, text="", json_data=None):
        self.status_code = status_code
        self.url = url
        self.text = text
        self._json_data = json_data or {}
        self.headers = {}

    def json(self):
        return self._json_data


def test_parse_winget_upgrade_standard_uses_strict_contract():
    sample_output = """Name                           Id                           Version          Available        Source
------------------------------------------------------------------------------------------------------
Google Chrome                  Google.Chrome                120.0.6099.110   120.0.6099.130   winget
Microsoft Visual Studio Code   Microsoft.VisualStudioCode   1.85.1           1.85.2           winget
"""
    results = parse_winget_upgrade(sample_output)

    assert len(results) == 2
    assert results[0]["Name"] == "Google Chrome"
    assert results[0]["Id"] == "Google.Chrome"
    assert results[0]["Version"] == "120.0.6099.110"
    assert results[0]["Available"] == "120.0.6099.130"
    assert results[0]["Source"] == "winget"
    assert results[1]["Id"] == "Microsoft.VisualStudioCode"


def test_parse_winget_upgrade_no_updates():
    assert parse_winget_upgrade("No applicable update found.") == []


def test_parse_winget_upgrade_empty_fails_closed():
    with pytest.raises(WingetParseError, match="empty output"):
        parse_winget_upgrade("")


def test_parse_winget_upgrade_with_unknown():
    sample_output = """Name                           Id                           Version          Available        Source
------------------------------------------------------------------------------------------------------
Some App                       Some.App                     unknown          1.2.3            winget
"""
    results = parse_winget_upgrade(sample_output, reg_data=[])
    assert len(results) == 1
    assert results[0]["Version"] == "unknown"


def test_parse_winget_upgrade_does_not_guess_from_name():
    sample_output = """Name                           Id                           Version          Available        Source
------------------------------------------------------------------------------------------------------
App 4.1.36                     Some.App                     unknown          4.1.36           winget
"""
    results = parse_winget_upgrade(sample_output, reg_data=[])

    assert len(results) == 1
    assert results[0]["Version"] == "unknown"


def test_parse_winget_upgrade_keeps_uncertain_winget_versions():
    sample_output = """Name                           Id                           Version          Available        Source
------------------------------------------------------------------------------------------------------
MEGAsync                       Mega.MEGASync                < 6.3.0.1        6.3.0.1          winget
"""
    results = parse_winget_upgrade(sample_output, reg_data=[])

    assert len(results) == 1
    assert results[0]["Version"] == "< 6.3.0.1"


def test_check_remote_version_facade_uses_hardened_detector(monkeypatch):
    responses = {
        "https://api.github.com/repos/owner/repo/releases/latest": FakeResponse(
            404,
            "https://api.github.com/repos/owner/repo/releases/latest",
        ),
        "https://github.com/owner/repo/releases/latest": FakeResponse(
            200,
            "https://github.com/owner/repo/releases/tag/v2.0.1",
        ),
    }

    def fake_safe_get(url, **kwargs):
        return responses[url]

    monkeypatch.setattr("src.logic.remote_versions.safe_get", fake_safe_get)

    assert (
        check_remote_version(
            "https://github.com/owner/repo",
            installed_version="2.0.0",
        )
        == "2.0.1"
    )


def test_check_remote_version_facade_does_not_scrape_github_page_text(
    monkeypatch,
):
    responses = {
        "https://api.github.com/repos/GNOME/gimp/releases/latest": FakeResponse(
            404,
            "https://api.github.com/repos/GNOME/gimp/releases/latest",
        ),
        "https://github.com/GNOME/gimp/releases/latest": FakeResponse(
            200,
            "https://github.com/GNOME/gimp/releases",
            "stars 4.835 watchers 10.303",
        ),
    }

    monkeypatch.setattr(
        "src.logic.remote_versions.safe_get",
        lambda url, **kwargs: responses[url],
    )

    assert (
        check_remote_version(
            "https://github.com/GNOME/gimp/releases",
            installed_version="2.10.38",
        )
        is None
    )


# --- Version comparison compatibility ---

def test_is_version_newer_basic():
    assert is_version_newer("2.0", "1.0") is True
    assert is_version_newer("1.0", "2.0") is False
    assert is_version_newer("1.0", "1.0") is False


def test_is_version_newer_multi_part():
    assert is_version_newer("1.2.3", "1.2.2") is True
    assert is_version_newer("1.2.2", "1.2.3") is False
    assert is_version_newer(
        "120.0.6099.130", "120.0.6099.110"
    ) is True


def test_is_version_newer_different_lengths():
    assert is_version_newer("1.1", "1.0.0.0") is True
    assert is_version_newer("1.0", "1.0.0.1") is False


def test_is_version_newer_with_v_prefix():
    assert is_version_newer("v2.0", "v1.0") is True
    assert is_version_newer("V1.0", "V2.0") is False


def test_is_version_newer_invalid_input():
    assert is_version_newer("abc", "1.0") is False
    assert is_version_newer("1.0", "") is False
    assert is_version_newer("", "") is False
    assert is_version_newer(None, "1.0") is False


def test_is_valid_version():
    assert is_valid_version("1.0") is True
    assert is_valid_version("1.2.3.4") is True
    assert is_valid_version("120.0.6099.130") is True
    assert is_valid_version("1.2.3.4.5") is False
    assert is_valid_version("") is False
    assert is_valid_version(None) is False
    assert is_valid_version("99999.0") is False


def test_parse_version_tuple():
    assert parse_version_tuple("1.2.3") == (1, 2, 3)
    assert parse_version_tuple("v1.0") == (1, 0)
    assert parse_version_tuple("abc") is None
    assert parse_version_tuple("") is None
    assert parse_version_tuple(None) is None


# --- Hardened URL compatibility aliases ---

def test_is_safe_url_allows_https():
    assert _is_safe_url("https://example.com") is True
    assert _is_safe_url("https://github.com/owner/repo") is True


def test_is_safe_url_rejects_non_https_and_credentials():
    assert _is_safe_url("http://example.com") is False
    assert _is_safe_url("ftp://example.com") is False
    assert _is_safe_url("file:///etc/passwd") is False
    assert _is_safe_url("https://user:secret@example.com") is False
    assert _is_safe_url("") is False
    assert _is_safe_url(None) is False
