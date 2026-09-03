from click.testing import CliRunner

from src import cli as cli_module
from src.app_info import get_app_version
from src.logic import diagnostics as diagnostics_module
from src.logic import config as config_module


def test_cli_help_preserves_complete_command_surface():
    result = CliRunner().invoke(cli_module.cli, ["--help"])
    assert result.exit_code == 0, result.output
    for command in (
        "check",
        "detective",
        "doctor",
        "ignored",
        "inventory",
        "search",
        "status",
        "update",
    ):
        assert command in result.output


def test_cli_version_uses_application_version():
    result = CliRunner().invoke(cli_module.cli, ["--version"])
    assert result.exit_code == 0, result.output
    assert get_app_version() in result.output
    assert "Winget Universal Dashboard" in result.output


def test_doctor_human_output_is_support_friendly_and_non_secret(monkeypatch):
    monkeypatch.setattr(
        diagnostics_module,
        "collect_diagnostics",
        lambda: {
            "application": {
                "version": "1.2.3",
                "commit": "a" * 40,
                "frozen": True,
            },
            "runtime": {
                "python": "3.12.10",
                "pyside6": "6.11.2",
                "platform": "Windows-test",
                "architecture": "AMD64",
            },
            "winget": {"version": "v1.test"},
            "settings": {
                "config_dir": "C:/config",
                "github_pat_configured": True,
                "ignored_updates_count": 2,
            },
        },
    )

    result = CliRunner().invoke(cli_module.cli, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "Version: 1.2.3" in result.output
    assert "Winget: v1.test" in result.output
    assert "GitHub PAT configured: yes" in result.output
    assert "No credential values are included" in result.output


def test_doctor_json_output_is_machine_readable(monkeypatch):
    payload = {
        "application": {"version": "1.2.3"},
        "runtime": {},
        "winget": {},
        "settings": {"github_pat_configured": False},
    }
    monkeypatch.setattr(diagnostics_module, "collect_diagnostics", lambda: payload)
    result = CliRunner().invoke(
        cli_module.cli, ["--json-output", "doctor"]
    )
    assert result.exit_code == 0, result.output
    assert '"version": "1.2.3"' in result.output


def test_ignored_command_lists_and_clears(monkeypatch):
    class FakeConfig:
        def __init__(self):
            self.ignored_updates = ["id:a.app|source:winget"]
            self.cleared = False

        def clear_ignored_updates(self):
            self.cleared = True
            self.ignored_updates = []

    fake = FakeConfig()
    monkeypatch.setattr(config_module, "ConfigManager", lambda: fake)

    listed = CliRunner().invoke(cli_module.cli, ["ignored"])
    assert listed.exit_code == 0, listed.output
    assert "id:a.app|source:winget" in listed.output

    cleared = CliRunner().invoke(cli_module.cli, ["ignored", "--clear"])
    assert cleared.exit_code == 0, cleared.output
    assert "Restored 1 ignored package update(s)" in cleared.output
    assert fake.cleared is True
