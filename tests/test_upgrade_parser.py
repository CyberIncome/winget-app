import unicodedata

import pytest

from src.logic.upgrade_parser import (
    WingetParseError,
    parse_upgrade_table,
    parse_winget_upgrade_strict,
)


def _width(text):
    total = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        total += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
    return total


def _row(fields, starts):
    result = fields[0]
    for field, target in zip(fields[1:], starts[1:]):
        padding = target - _width(result)
        assert padding >= 1
        result += " " * padding + field
    return result


def test_parse_upgrade_table_standard():
    output = """Name                           Id                           Version          Available        Source
------------------------------------------------------------------------------------------------------
Google Chrome                  Google.Chrome                120.0.6099.110   120.0.6099.130   winget
Microsoft Visual Studio Code   Microsoft.VisualStudioCode   1.85.1           1.85.2           winget
"""
    assert parse_upgrade_table(output) == [
        {
            "Name": "Google Chrome",
            "Id": "Google.Chrome",
            "Version": "120.0.6099.110",
            "Available": "120.0.6099.130",
            "Source": "winget",
        },
        {
            "Name": "Microsoft Visual Studio Code",
            "Id": "Microsoft.VisualStudioCode",
            "Version": "1.85.1",
            "Available": "1.85.2",
            "Source": "winget",
        },
    ]


def test_parse_upgrade_table_without_source_column():
    output = """Name                    Id                    Version      Available
------------------------------------------------------------------------
Example App             Example.App           1.0.0        1.1.0
"""
    rows = parse_upgrade_table(output)
    assert rows[0]["Id"] == "Example.App"
    assert rows[0]["Available"] == "1.1.0"
    assert rows[0]["Source"] == ""


def test_parse_localized_german_header_and_truncated_id():
    output = """Name                                   ID                                      Version          Verfügbar        Quelle
-----------------------------------------------------------------------------------------------------------------------
Microsoft .NET Framework 4.5 SDK       Microsoft.DotNet.Framework.DeveloperPa…     < 4.6.2          4.6.2            winget
1 Aktualisierung verfügbar.
"""

    rows = parse_upgrade_table(output)

    assert rows == [
        {
            "Name": "Microsoft .NET Framework 4.5 SDK",
            "Id": "Microsoft.DotNet.Framework.DeveloperPa…",
            "Version": "< 4.6.2",
            "Available": "4.6.2",
            "Source": "winget",
        }
    ]


def test_parse_cjk_header_and_full_width_name_by_display_columns():
    starts = [0, 32, 64, 80, 96]
    header = _row(
        ["名前", "ID", "バージョン", "利用可能", "ソース"],
        starts,
    )
    data = _row(
        ["日本語 アプリ", "Example.Cjk.App", "1.0.0", "1.1.0", "winget"],
        starts,
    )
    output = f"{header}\n{'-' * 110}\n{data}\n"

    rows = parse_upgrade_table(output)

    assert rows[0] == {
        "Name": "日本語 アプリ",
        "Id": "Example.Cjk.App",
        "Version": "1.0.0",
        "Available": "1.1.0",
        "Source": "winget",
    }


def test_parse_when_available_field_leaves_only_one_space_before_source():
    starts = [0, 24, 48, 60, 64]
    header = _row(["Name", "Id", "Ver", "A", "Src"], starts)
    # "1.1" occupies three of the four display cells in this localized table's
    # Available column, leaving exactly one separating space before Source.
    data = _row(
        ["Example App", "Example.App", "1.0", "1.1", "Private Feed"],
        starts,
    )
    output = f"{header}\n{'-' * 90}\n{data}\n"

    rows = parse_upgrade_table(output)

    assert rows[0]["Available"] == "1.1"
    assert rows[0]["Source"] == "Private Feed"


def test_no_updates_is_empty():
    assert parse_upgrade_table("No applicable update found.") == []


def test_empty_output_is_explicit_failure():
    with pytest.raises(WingetParseError, match="empty output"):
        parse_upgrade_table("")
    with pytest.raises(WingetParseError, match="empty output"):
        parse_upgrade_table("  \r\n  ")


def test_missing_required_column_is_explicit_failure():
    output = """Name                    Id                    Version
------------------------------------------------------------
Example App             Example.App           1.0.0
"""
    with pytest.raises(WingetParseError):
        parse_upgrade_table(output)


def test_header_without_separator_is_explicit_failure():
    output = """Name                    Id                    Version      Available
Example App             Example.App           1.0.0        1.1.0
"""
    with pytest.raises(WingetParseError):
        parse_upgrade_table(output)


def test_unrecognized_error_output_does_not_become_zero_updates():
    with pytest.raises(WingetParseError):
        parse_upgrade_table("Failed when opening source(s); unexpected error")


def test_partial_malformed_table_fails_instead_of_returning_subset():
    output = """Name                    Id                    Version      Available       Source
------------------------------------------------------------------------------------
Good App                Good.App              1.0.0        1.1.0           winget
broken
"""
    with pytest.raises(WingetParseError, match="malformed data row"):
        parse_upgrade_table(output)


def test_empty_table_without_no_update_marker_fails():
    output = """Name                    Id                    Version      Available       Source
------------------------------------------------------------------------------------
"""
    with pytest.raises(WingetParseError, match="no package rows"):
        parse_upgrade_table(output)


def test_strict_parser_never_vetoes_winget_reported_upgrade():
    output = """Name                    Id                    Version      Available       Source
------------------------------------------------------------------------------------
Vendor Channel App      Vendor.Channel.App    1.0-beta     1.0             winget
"""

    rows = parse_winget_upgrade_strict(output, reg_data=[])

    assert len(rows) == 1
    assert rows[0]["Id"] == "Vendor.Channel.App"
    assert rows[0]["Version"] == "1.0-beta"
    assert rows[0]["Available"] == "1.0"


def test_known_versions_do_not_require_windows_registry_imports():
    output = """Name                    Id                    Version      Available       Source
------------------------------------------------------------------------------------
Example App             Example.App           5.0          4.9             winget
"""

    rows = parse_winget_upgrade_strict(output)

    assert len(rows) == 1
    assert rows[0]["Version"] == "5.0"
    assert rows[0]["Available"] == "4.9"
