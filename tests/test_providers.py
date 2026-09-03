from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.logic.command_runner import CommandResult
from src.providers.base import (
    ActionKind,
    ProviderAction,
    ProviderCategory,
    ProviderMode,
    ProviderScanResult,
    ProviderStatus,
    ProviderUpdate,
)
from src.providers.chocolatey import (
    ChocolateyProvider,
    parse_chocolatey_outdated,
)
from src.providers.npm import NpmGlobalProvider, parse_npm_outdated
from src.providers.pipx import PipxProvider, parse_pipx_outdated
from src.providers.registry import ProviderRegistry
from src.providers.steam import (
    SteamProvider,
    parse_app_manifest,
    parse_library_folders,
)


def _result(
    stdout: str = "",
    *,
    returncode: int = 0,
    stderr: str = "",
) -> CommandResult:
    return CommandResult(
        command=("fake",),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _update(
    provider_id: str = "example",
    *,
    can_update: bool = True,
) -> ProviderUpdate:
    return ProviderUpdate(
        provider_id=provider_id,
        item_id="pkg",
        name="Package",
        installed_version="1.0",
        available_version="2.0",
        category=ProviderCategory.APPLICATION,
        mode=ProviderMode.MANAGED,
        can_update=can_update,
    )


def test_provider_update_identity_is_provider_scoped():
    assert _update("alpha").identity == "alpha:pkg"
    assert _update("beta").identity == "beta:pkg"


def test_provider_update_rejects_invalid_provider_id():
    with pytest.raises(ValueError):
        _update("Not Valid!")


def test_informational_update_cannot_claim_direct_execution():
    with pytest.raises(ValueError):
        ProviderUpdate(
            provider_id="info",
            item_id="pkg",
            name="Package",
            installed_version="1",
            available_version="2",
            category=ProviderCategory.OTHER,
            mode=ProviderMode.INFORMATIONAL,
            can_update=True,
        )


def test_managed_executable_update_requires_exact_target():
    with pytest.raises(ValueError):
        ProviderUpdate(
            provider_id="managed",
            item_id="pkg",
            name="Package",
            installed_version="1",
            available_version=None,
            category=ProviderCategory.OTHER,
            mode=ProviderMode.MANAGED,
            can_update=True,
        )


def test_command_action_requires_target_version():
    with pytest.raises(ValueError):
        ProviderAction(
            provider_id="managed",
            item_id="pkg",
            kind=ActionKind.COMMAND,
            command=("tool", "upgrade", "pkg"),
        )


class _Provider:
    provider_id = "alpha"

    def probe(self):
        return ProviderStatus(
            provider_id=self.provider_id,
            display_name="Alpha",
            mode=ProviderMode.MANAGED,
            category=ProviderCategory.OTHER,
            available=True,
        )

    def scan_updates(self):
        return ProviderScanResult(status=self.probe(), updates=(_update("alpha"),))

    def plan_update(self, update):
        raise NotImplementedError


def test_registry_rejects_duplicate_provider_ownership():
    with pytest.raises(ValueError):
        ProviderRegistry([_Provider(), _Provider()])


def test_registry_keeps_scan_exception_provider_local():
    class Broken(_Provider):
        def scan_updates(self):
            raise RuntimeError("boom")

    result = ProviderRegistry([Broken()]).scan_all()[0]
    assert result.ok is False
    assert "boom" in result.error


def test_registry_rejects_cross_provider_update_records():
    class Confused(_Provider):
        def scan_updates(self):
            return ProviderScanResult(
                status=self.probe(),
                updates=(_update("beta"),),
            )

    result = ProviderRegistry([Confused()]).scan_all()[0]
    assert result.ok is False
    assert "another provider" in result.error


def test_parse_steam_manifest_requires_appid_buildid_and_name():
    text = '''
"AppState"
{
    "appid"        "1234"
    "Universe"     "1"
    "name"         "Example Game"
    "StateFlags"   "4"
    "installdir"   "Example Game"
    "buildid"      "98765"
}
'''
    assert parse_app_manifest(text) == {
        "appid": "1234",
        "buildid": "98765",
        "name": "Example Game",
        "installdir": "Example Game",
    }
    assert parse_app_manifest('"appid" "1"\n"name" "Broken"') is None


def test_parse_steam_libraryfolders_reads_only_path_fields():
    text = r'''
"libraryfolders"
{
    "0"
    {
        "path" "C:\\Program Files (x86)\\Steam"
    }
    "1"
    {
        "path" "D:\\SteamLibrary"
    }
}
'''
    assert parse_library_folders(text) == (
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"D:\SteamLibrary"),
    )


class _SteamResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def test_steam_provider_discovers_manifest_and_reports_update(tmp_path):
    steam_root = tmp_path / "Steam"
    steamapps = steam_root / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "libraryfolders.vdf").write_text(
        f'"path" "{str(steam_root).replace(chr(92), chr(92) * 2)}"',
        encoding="utf-8",
    )
    (steamapps / "appmanifest_1234.acf").write_text(
        '"appid" "1234"\n'
        '"name" "Example Game"\n'
        '"installdir" "Example Game"\n'
        '"buildid" "10"\n',
        encoding="utf-8",
    )

    calls = []

    def getter(url, **kwargs):
        calls.append((url, kwargs))
        return _SteamResponse(
            {
                "response": {
                    "success": True,
                    "up_to_date": False,
                    "required_version": 11,
                    "version_is_listable": True,
                }
            }
        )

    provider = SteamProvider(roots=(steam_root,), getter=getter)
    result = provider.scan_updates()
    assert result.ok is True
    assert len(result.updates) == 1
    update = result.updates[0]
    assert update.provider_id == "steam"
    assert update.item_id == "1234"
    assert update.installed_version == "10"
    assert update.available_version == "11"
    assert update.can_update is False
    assert calls[0][1]["params"] == {"appid": 1234, "version": 10}
    action = provider.plan_update(update)
    assert action.kind == ActionKind.HANDOFF
    assert action.uri == "steam://open/downloads"


def test_steam_provider_warning_does_not_invent_update(tmp_path):
    steam_root = tmp_path / "Steam"
    steamapps = steam_root / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "appmanifest_7.acf").write_text(
        '"appid" "7"\n"name" "Game"\n"buildid" "4"\n',
        encoding="utf-8",
    )

    def getter(*_args, **_kwargs):
        raise TimeoutError("network timeout")

    result = SteamProvider(roots=(steam_root,), getter=getter).scan_updates()
    assert result.updates == ()
    assert len(result.warnings) == 1
    assert "network timeout" in result.warnings[0]


def test_chocolatey_parser_respects_pins_and_malformed_lines():
    updates = parse_chocolatey_outdated(
        "git|2.0|2.1|false\n"
        "python|3.12|3.13|true\n"
        "not-a-record\n"
    )
    assert [item.item_id for item in updates] == ["git", "python"]
    assert updates[0].can_update is True
    assert updates[1].can_update is False
    assert "pinned" in updates[1].blocked_reason.lower()


def test_chocolatey_scan_accepts_enhanced_outdated_exit_code():
    calls = []

    def runner(command, timeout):
        calls.append(tuple(command))
        if command[-1] == "--version":
            return _result("2.5.0\n")
        return _result("git|2.0|2.1|false\n", returncode=2)

    provider = ChocolateyProvider(runner=runner, executable="choco.exe")
    result = provider.scan_updates()
    assert result.ok is True
    assert len(result.updates) == 1
    assert result.status.version == "2.5.0"
    assert calls[-1][1:] == ("outdated", "--limit-output", "--no-color")


def test_chocolatey_plan_pins_exact_scanned_target():
    provider = ChocolateyProvider(executable="choco.exe")
    update = parse_chocolatey_outdated("git|2.0|2.1|false")[0]
    action = provider.plan_update(update)
    assert action.kind == ActionKind.COMMAND
    assert action.target_version == "2.1"
    assert action.command == (
        "choco.exe",
        "upgrade",
        "git",
        "--version",
        "2.1",
        "--yes",
        "--no-progress",
    )


def test_pipx_parser_uses_structured_outdated_envelope():
    payload = {
        "pipx_result_version": "1",
        "command": ["list"],
        "status": "success",
        "exit_code": 0,
        "data": {
            "packages": [
                {
                    "environment": "black",
                    "package": "black",
                    "version": "24.1",
                    "latest_version": "25.1",
                    "injected": False,
                    "pinned": False,
                },
                {
                    "environment": "ruff-tools",
                    "package": "ruff",
                    "version": "0.1",
                    "latest_version": "0.2",
                    "injected": False,
                    "pinned": False,
                },
            ]
        },
        "errors": [],
    }
    updates = parse_pipx_outdated(json.dumps(payload))
    assert updates[0].can_update is True
    assert updates[1].can_update is False
    assert "suffixed" in updates[1].blocked_reason


def test_pipx_plan_uses_exact_install_upgrade_spec():
    payload = {
        "status": "success",
        "data": {
            "packages": [
                {
                    "environment": "black",
                    "package": "black",
                    "version": "24.1",
                    "latest_version": "25.1",
                }
            ]
        },
    }
    update = parse_pipx_outdated(json.dumps(payload))[0]
    action = PipxProvider(executable="pipx.exe").plan_update(update)
    assert action.kind == ActionKind.COMMAND
    assert action.target_version == "25.1"
    assert action.command == (
        "pipx.exe",
        "install",
        "black==25.1",
        "--upgrade",
        "--output=json",
    )


def test_npm_parser_uses_latest_global_target():
    updates = parse_npm_outdated(
        json.dumps(
            {
                "typescript": {
                    "current": "5.8.0",
                    "wanted": "5.9.0",
                    "latest": "5.9.0",
                    "location": "global/node_modules/typescript",
                }
            }
        )
    )
    assert len(updates) == 1
    assert updates[0].item_id == "typescript"
    assert updates[0].available_version == "5.9.0"


def test_npm_scan_accepts_exit_one_only_when_json_is_valid():
    def runner(command, timeout):
        if command[-1] == "--version":
            return _result("12.0.2\n")
        return _result(
            json.dumps(
                {
                    "typescript": {
                        "current": "5.8.0",
                        "wanted": "5.9.0",
                        "latest": "5.9.0",
                    }
                }
            ),
            returncode=1,
        )

    result = NpmGlobalProvider(runner=runner, executable="npm.cmd").scan_updates()
    assert result.ok is True
    assert len(result.updates) == 1
    assert result.warnings


def test_npm_plan_uses_exact_global_package_spec():
    update = parse_npm_outdated(
        json.dumps(
            {
                "typescript": {
                    "current": "5.8.0",
                    "latest": "5.9.0",
                }
            }
        )
    )[0]
    action = NpmGlobalProvider(executable="npm.cmd").plan_update(update)
    assert action.kind == ActionKind.COMMAND
    assert action.target_version == "5.9.0"
    assert action.command == (
        "npm.cmd",
        "install",
        "--global",
        "typescript@5.9.0",
    )
