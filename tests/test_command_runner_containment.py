from src.logic.command_runner import CommandResult


def test_containment_error_is_terminal_failure():
    result = CommandResult(
        command=("winget", "show"),
        returncode=0,
        stdout="ok",
        stderr="",
        containment_error="CloseHandle(job) failed",
    )
    assert result.ok is False
    assert result.failure_summary() == (
        "process-tree containment failed: CloseHandle(job) failed"
    )
