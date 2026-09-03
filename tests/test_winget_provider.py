from __future__ import annotations

from src.logic.command_runner import CommandResult
from src.providers.base import ActionKind, ProviderCategory
from src.providers.winget import WingetProvider, winget_rows_to_provider_updates


def _result(stdout="", returncode=0):
    return CommandResult(
        command=("fake",),
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


def test_winget_rows_preserve_source_and_version_provenance():
    updates = winget_rows_to_provider_updates(
        [
            {
                "Name": "Example",
                "Id": "Vendor.Example",
                "Version": "1.0.0",
                "Available": "2.0.0",
                "Source": "winget",
            },
            {
                "Name": "Store Example",
                "Id": "9NEXAMPLE",
                "Version": "1.0",
                "Available": "2.0",
                "Source": "msstore",
            },
        ]
    )
    assert updates[0].provider_id == "winget"
    assert updates[0].source == "winget"
    assert updates[0].category == ProviderCategory.APPLICATION
    assert updates[0].metadata["version_status"] == "direct-upgrade"
    assert updates[1].source == "msstore"
    assert updates[1].category == ProviderCategory.STORE


def test_winget_rows_skip_incomplete_target_records():
    updates = winget_rows_to_provider_updates(
        [
            {
                "Name": "Missing target",
                "Id": "Vendor.Missing",
                "Version": "1.0",
                "Available": "",
                "Source": "winget",
            },
            {
                "Name": "Missing id",
                "Id": "",
                "Version": "1.0",
                "Available": "2.0",
                "Source": "winget",
            },
        ]
    )
    assert updates == ()


def test_winget_plan_uses_exact_source_and_scanned_target():
    update = winget_rows_to_provider_updates(
        [
            {
                "Name": "Example",
                "Id": "Vendor.Example",
                "Version": "1.0.0",
                "Available": "2.0.0",
                "Source": "winget",
            }
        ]
    )[0]
    action = WingetProvider(executable="winget.exe").plan_update(update)
    assert action.kind == ActionKind.COMMAND
    assert action.target_version == "2.0.0"
    assert action.command == (
        "winget.exe",
        "upgrade",
        "--id",
        "Vendor.Example",
        "--exact",
        "--source",
        "winget",
        "--version",
        "2.0.0",
        "--silent",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    )


def test_winget_scan_fails_closed_on_nonzero_result():
    calls = []

    def runner(command, timeout):
        calls.append((tuple(command), timeout))
        if command[-1] == "--version":
            return _result("v1.29.0\n")
        return _result("partial output", returncode=1)

    result = WingetProvider(
        runner=runner,
        registry_loader=lambda: [],
        executable="winget.exe",
    ).scan_updates()
    assert result.ok is False
    assert result.updates == ()
    assert "exited with code 1" in result.error


def test_winget_scan_uses_strict_parser_and_registry_provenance():
    table = """
Name        Id              Version  Available  Source
-----------------------------------------------------
Example     Vendor.Example  1.0      2.0        winget
1 upgrades available.
"""

    def runner(command, timeout):
        if command[-1] == "--version":
            return _result("v1.29.0\n")
        return _result(table)

    result = WingetProvider(
        runner=runner,
        registry_loader=lambda: [],
        executable="winget.exe",
    ).scan_updates()
    assert result.ok is True
    assert len(result.updates) == 1
    assert result.updates[0].item_id == "Vendor.Example"
    assert result.updates[0].available_version == "2.0"
