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
