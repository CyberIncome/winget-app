"""Regression tests for process-output memory bounds."""

from __future__ import annotations

from src.ui.runtime_window import RuntimeMainWindow


def test_console_history_has_original_finite_block_limit(qtbot):
    window = RuntimeMainWindow()
    qtbot.addWidget(window)

    assert window.console.maximumBlockCount() == 2_000


def test_unterminated_process_line_is_bounded(qtbot):
    window = RuntimeMainWindow()
    qtbot.addWidget(window)

    window._handle_process_output("stdout", "x" * (64 * 1024))

    assert len(window._terminal_line_buffer) <= window._terminal_line_limit
    assert window._terminal_line_buffer == (
        "x" * window._terminal_line_limit
    )


def test_completed_lines_survive_while_oversized_live_tail_is_bounded(qtbot):
    window = RuntimeMainWindow()
    qtbot.addWidget(window)

    window._handle_process_output(
        "stdout",
        "completed line\n" + ("y" * (64 * 1024)),
    )

    assert "completed line" in window.console.toPlainText()
    assert len(window._terminal_line_buffer) <= window._terminal_line_limit
    assert window._terminal_line_buffer == (
        "y" * window._terminal_line_limit
    )
