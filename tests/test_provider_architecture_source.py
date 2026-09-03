from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_production_gui_does_not_dispatch_provider_actions_during_phase_a():
    main_source = _source("src/main.py")
    authoritative_source = _source("src/ui/authoritative_updates_window.py")
    progress_source = _source("src/ui/update_progress.py")
    assert "src.providers" not in main_source
    assert "src.providers" not in authoritative_source
    assert "src.providers" not in progress_source


def test_provider_developer_cli_is_read_only_scan_surface():
    source = _source("src/providers/cli.py")
    assert 'choices=("status", "scan")' in source
    assert "plan_update" not in source
    assert "run_command" not in source
    assert "subprocess" not in source


def test_provider_registry_enforces_exact_owner_and_target_before_execution_phase():
    source = _source("src/providers/registry.py")
    assert "provider action changed provider ownership" in source
    assert "provider action changed item identity" in source
    assert "provider action target does not match scanned target" in source
    assert "provider planned a command for a blocked update" in source


def test_provider_command_modules_use_bounded_runner_not_shell_invocation():
    for path in (
        "src/providers/winget.py",
        "src/providers/chocolatey.py",
        "src/providers/pipx.py",
        "src/providers/npm.py",
        "src/providers/epic_legendary.py",
    ):
        source = _source(path)
        assert "from src.logic.command_runner" in source
        assert "shell=True" not in source
        assert "os.system(" not in source
        assert "subprocess.Popen" not in source


def test_steam_provider_uses_hardened_https_helper_and_handoff_only():
    source = _source("src/providers/steam.py")
    assert "from src.logic.http_safety import safe_get" in source
    assert "steam://open/downloads" in source
    assert "SteamCMD" in source
    assert "ActionKind.COMMAND" not in source


def test_epic_provider_cannot_authenticate_or_update_implicitly():
    source = _source("src/providers/epic_legendary.py")
    assert 'requires_opt_in=True' in source
    assert '"list-installed"' in source
    assert '"--check-updates"' in source
    assert "ActionKind.NONE" in source
    assert '"auth"' not in source
    assert '"install"' not in source
    assert '"update-only"' not in source


def test_multi_provider_design_document_preserves_release_acceptance_rule():
    source = _source("docs/MULTI_PROVIDER.md")
    assert "Provider identity is part of update identity" in source
    assert "A scan failure is not zero updates" in source
    assert "No cross-provider dispatch" in source
    assert "No UI automation as an update protocol" in source
    assert "Universal Update All" in source
