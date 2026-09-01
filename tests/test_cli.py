from click.testing import CliRunner

from src import cli as cli_module
from src.logic.command_runner import CommandResult
from src.logic.executor import WingetExecutor


def test_run_upgrade_scan_uses_hardened_executor_command(monkeypatch):
    captured = {}

    def fake_run_command(command, timeout=300):
        captured["command"] = list(command)
        captured["timeout"] = timeout
        return CommandResult(tuple(command), 0, "ok", "")

    monkeypatch.setattr(cli_module, "run_command", fake_run_command)

    result = cli_module.run_upgrade_scan(timeout=42)

    assert result.ok
    assert captured["command"] == WingetExecutor().get_check_updates_cmd()
    assert captured["timeout"] == 42


def test_print_table_accepts_source_column(capsys):
    cli_module.print_table(
        [
            {
                "Name": "Example",
                "Id": "Example.App",
                "Version": "1.0",
                "Available": "1.1",
                "Source": "private-feed",
            }
        ],
        ["Name", "Id", "Version", "Available", "Source"],
    )

    output = capsys.readouterr().out
    assert "Source" in output
    assert "private-feed" in output


def test_specific_update_carries_source_to_exact_command(monkeypatch):
    captured = []
    monkeypatch.setattr(
        cli_module,
        "_run_update_live",
        lambda command: captured.append(command),
    )

    result = CliRunner().invoke(
        cli_module.cli,
        ["update", "--source", "private-feed", "Shared.App"],
    )

    assert result.exit_code == 0, result.output
    assert captured == [
        WingetExecutor().get_update_cmd(
            "Shared.App",
            source="private-feed",
        )
    ]


def test_update_all_rejects_source_instead_of_ignoring_it(monkeypatch):
    captured = []
    monkeypatch.setattr(
        cli_module,
        "_run_update_live",
        lambda command: captured.append(command),
    )

    result = CliRunner().invoke(
        cli_module.cli,
        ["update", "--all", "--source", "private-feed"],
    )

    assert result.exit_code != 0
    assert "--source applies only" in result.output
    assert captured == []
