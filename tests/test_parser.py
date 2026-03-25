import pytest
from src.logic.parser import (
    parse_winget_upgrade,
    is_version_newer,
    is_valid_version,
    parse_version_tuple,
    _is_safe_url,
)


def test_parse_winget_upgrade_standard():
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
    assert "Source" not in results[0]

    assert results[1]["Id"] == "Microsoft.VisualStudioCode"


def test_parse_winget_upgrade_no_updates():
    sample_output = "No applicable update found."
    results = parse_winget_upgrade(sample_output)
    assert results == []


def test_parse_winget_upgrade_empty():
    results = parse_winget_upgrade("")
    assert results == []


def test_parse_winget_upgrade_with_unknown():
    sample_output = """Name                           Id                           Version          Available        Source
------------------------------------------------------------------------------------------------------
Some App                       Some.App                     unknown          1.2.3            winget
"""
    results = parse_winget_upgrade(sample_output)
    assert len(results) == 1
    assert results[0]["Version"] == "unknown"


# --- Version comparison tests (was 0% coverage) ---

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
    """Shorter tuples are padded with zeros."""
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


# --- C2: URL safety tests ---

def test_is_safe_url_allows_https():
    assert _is_safe_url("https://example.com") is True
    assert _is_safe_url(
        "https://github.com/owner/repo"
    ) is True


def test_is_safe_url_rejects_non_https():
    assert _is_safe_url("http://example.com") is False
    assert _is_safe_url("ftp://example.com") is False
    assert _is_safe_url("file:///etc/passwd") is False
    assert _is_safe_url("") is False
    assert _is_safe_url(None) is False
