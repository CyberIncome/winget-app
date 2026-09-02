import os

from src.main import main


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


def test_main_initialization(qtbot):
    assert main() == 0
