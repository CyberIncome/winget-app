"""Regression coverage for truncated Winget package identifiers."""

from __future__ import annotations

from src.ui.production_window import ProductionMainWindow


def test_ascii_truncated_id_falls_back_to_exact_name_and_source(qtbot):
    window = ProductionMainWindow()
    qtbot.addWidget(window)

    item = {
        "Name": "Visual Studio Build Tools 2022",
        "Id": "Microsoft.VisualStudio.2022.BuildToo...",
        "Version": "17.14.27",
        "Available": "17.14.28",
        "Source": "winget",
        "UpdateSource": "winget",
    }

    ref = window._package_ref_for_winget_item(item)

    assert ref == {
        "value": "Visual Studio Build Tools 2022",
        "match_by": "name",
        "source": "winget",
    }
    command = window.executor.get_update_cmd(
        ref["value"],
        ref["match_by"],
        source=ref["source"],
    )
    assert "--name" in command
    assert "--id" not in command
    assert "Microsoft.VisualStudio.2022.BuildToo..." not in command
