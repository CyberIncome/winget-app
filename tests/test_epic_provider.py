from __future__ import annotations

from src.logic.command_runner import CommandResult
from src.providers.base import ActionKind, ProviderMode
from src.providers.epic_legendary import (
    EpicLegendaryProvider,
    parse_legendary_installed_updates,
)


def _result(stdout="", returncode=0, stderr=""):
    return CommandResult(
        command=("legendary",),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _csv(*rows):
    header = (
        "App name,App title,Installed version,Available version,"
        "Update available,Install size,Install path,Platform\n"
    )
    return header + "\n".join(rows) + ("\n" if rows else "")


def test_legendary_csv_reports_only_explicit_updates():
    updates = parse_legendary_installed_updates(
        _csv(
            'Fortnite,Fortnite,1.0,1.1,True,123,"C:\\Games\\Fortnite",Windows',
            'Current,Current Game,2.0,2.0,False,456,"C:\\Games\\Current",Windows',
        )
    )
    assert len(updates) == 1
    update = updates[0]
    assert update.provider_id == "epic-legendary"
    assert update.item_id == "Fortnite"
    assert update.name == "Fortnite"
    assert update.installed_version == "1.0"
    assert update.available_version == "1.1"
    assert update.mode == ProviderMode.INFORMATIONAL
    assert update.can_update is False
    assert update.metadata["platform"] == "Windows"


def test_legendary_csv_schema_change_fails_closed():
    try:
        parse_legendary_installed_updates("App name,App title\nA,B\n")
    except ValueError as exc:
        assert "schema changed" in str(exc)
    else:
        raise AssertionError("schema change was accepted")


def test_epic_provider_is_unavailable_without_legendary():
    provider = EpicLegendaryProvider(executable=None)
    provider._executable = lambda: None
    status = provider.probe()
    assert status.available is False
    assert "optional" in status.reason.lower()


def test_epic_provider_scan_uses_check_updates_csv():
    calls = []

    def runner(command, timeout):
        calls.append((tuple(command), timeout))
        if command[-1] == "--version":
            return _result("legendary version 0.21.0\n")
        return _result(
            _csv(
                'GameApp,Game Title,1.0,2.0,True,123,"C:\\Games\\Game",Windows'
            )
        )

    provider = EpicLegendaryProvider(
        runner=runner,
        executable="legendary.exe",
    )
    result = provider.scan_updates()
    assert result.ok is True
    assert len(result.updates) == 1
    assert calls[-1] == (
        (
            "legendary.exe",
            "list-installed",
            "--check-updates",
            "--csv",
        ),
        300,
    )


def test_epic_provider_auth_failure_is_not_zero_updates():
    def runner(command, timeout):
        if command[-1] == "--version":
            return _result("legendary version 0.21.0\n")
        return _result("", returncode=1, stderr="Login failed")

    result = EpicLegendaryProvider(
        runner=runner,
        executable="legendary.exe",
    ).scan_updates()
    assert result.ok is False
    assert result.updates == ()
    assert "authentication may be required" in result.error.lower()


def test_epic_update_planning_stays_non_executable_until_exact_manifest_bound():
    update = parse_legendary_installed_updates(
        _csv(
            'GameApp,Game Title,1.0,2.0,True,123,"C:\\Games\\Game",Windows'
        )
    )[0]
    action = EpicLegendaryProvider(executable="legendary.exe").plan_update(update)
    assert action.kind == ActionKind.NONE
    assert action.command == ()
    assert "exact" in action.description.lower()
