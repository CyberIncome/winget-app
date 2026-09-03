from __future__ import annotations

from src.providers import cli


def test_status_output_marks_opt_in_provider(capsys):
    cli._print_status(
        [
            {
                "display_name": "Epic Games (Legendary)",
                "available": True,
                "requires_opt_in": True,
                "mode": "informational",
                "version": "0.21.0",
                "reason": None,
            }
        ]
    )
    output = capsys.readouterr().out
    assert "ready (opt-in)" in output
    assert "Epic Games (Legendary)" in output


def test_scan_output_distinguishes_opt_in_skip_from_zero_updates(capsys):
    cli._print_scan(
        [
            {
                "status": {
                    "display_name": "Epic Games (Legendary)",
                    "available": True,
                    "requires_opt_in": True,
                    "mode": "informational",
                },
                "updates": [],
                "warnings": [
                    "provider requires explicit opt-in and was not scanned"
                ],
                "error": None,
            }
        ]
    )
    output = capsys.readouterr().out
    assert "not scanned: explicit opt-in required" in output
    assert "no updates reported" not in output


def test_provider_cli_parser_exposes_status_scan_only():
    parser = cli.build_parser()
    assert parser.parse_args(["status"]).command == "status"
    args = parser.parse_args(["scan", "--provider", "steam"])
    assert args.command == "scan"
    assert args.provider == ["steam"]
