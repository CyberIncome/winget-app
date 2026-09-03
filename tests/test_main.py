import os
from pathlib import Path

from src.main import main


ROOT = Path(__file__).resolve().parents[1]


def test_qss_exists():
    qss_path = os.path.join("src", "ui", "styles.qss")
    assert os.path.exists(qss_path)
    with open(qss_path, "r", encoding="utf-8") as file_handle:
        content = file_handle.read()
    assert "QMainWindow" in content
    assert "#11131c" in content
    assert "QLabel#statBadge" in content
    assert "QWidget#updatesToolbar" in content
    assert "QWidget#actionBar" in content
    assert 'QPushButton[compact="true"]' in content
    assert "QScrollArea#settingsScroll" in content
    assert "QTableView::item:selected" in content
    # Table interaction is row-based. A per-cell hover background makes one
    # cell visually diverge from the row and can hide/reveal stale paint state.
    assert "QTableView::item:hover" not in content


def test_normal_main_arms_optimized_startup_before_legacy_fallback():
    source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    assert "QTimer.singleShot(100, window.startup_sequence)" in source
    assert 'os.getenv("WUD_PACKAGED_SMOKE") == "1"' in source
    assert "from src.ui.update_progress import apply_update_progress" in source
    assert "apply_update_progress(window)" in source


def test_main_initialization(qtbot):
    assert main() == 0
