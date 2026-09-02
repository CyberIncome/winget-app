from pathlib import Path

import pytest

from src.logic.executor import WingetExecutor, validate_output_path


def test_show_command_is_exact_source_aware_and_read_only():
    assert WingetExecutor().get_show_cmd(
        "Vendor.App", source="private-feed"
    ) == [
        "winget",
        "show",
        "--id",
        "Vendor.App",
        "--exact",
        "--source",
        "private-feed",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]


def test_show_by_name_validates_like_update_targeting():
    assert WingetExecutor().get_show_cmd(
        "Example App", match_by="name"
    )[:5] == ["winget", "show", "--name", "Example App", "--exact"]
    with pytest.raises(ValueError):
        WingetExecutor().get_show_cmd("--all", match_by="name")


def test_export_command_requires_absolute_path_and_can_include_versions(tmp_path):
    destination = tmp_path / "winget-backup.json"
    assert WingetExecutor().get_export_cmd(
        destination, include_versions=True
    ) == [
        "winget",
        "export",
        "--output",
        str(destination),
        "--include-versions",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]


def test_export_path_rejects_relative_and_control_characters(tmp_path):
    with pytest.raises(ValueError, match="absolute"):
        validate_output_path(Path("relative.json"))
    with pytest.raises(ValueError):
        validate_output_path(str(tmp_path / "bad\nname.json"))
