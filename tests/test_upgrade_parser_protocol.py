"""Regressions for modern WinGet multi-section upgrade output."""

import pytest

from src.logic.upgrade_parser import WingetParseError, parse_upgrade_table


def test_no_update_marker_followed_by_explicit_target_table_fails_closed():
    output = """No installed package found matching input criteria.

The following packages have an upgrade available, but require explicit targeting for upgrade:
Name                      Id                    Version  Available  Source
----------------------------------------------------------------------------
Chocolatey (Install Only) Chocolatey.Chocolatey 2.5.0.0  2.5.1.0    winget
1 package(s) are pinned and need to be explicitly upgraded.
"""

    with pytest.raises(WingetParseError, match="explicit targeting"):
        parse_upgrade_table(output)


def test_secondary_explicit_target_table_is_not_added_to_actionable_rows():
    output = """Name                    Id                    Version  Available  Source
----------------------------------------------------------------------------
Normal App              Vendor.Normal.App     1.0.0    1.1.0      winget
1 upgrades available.

The following packages have an upgrade available, but require explicit targeting for upgrade:
Name                    Id                    Version  Available  Source
----------------------------------------------------------------------------
Pinned App              Vendor.Pinned.App     2.0.0    2.1.0      winget
1 package(s) are pinned and need to be explicitly upgraded.
"""

    rows = parse_upgrade_table(output)

    assert [row["Id"] for row in rows] == ["Vendor.Normal.App"]


def test_plain_no_update_marker_without_table_still_means_zero():
    assert (
        parse_upgrade_table(
            "No installed package found matching input criteria."
        )
        == []
    )
