import os
import pytest
from PySide6.QtWidgets import QApplication
from src.main import main

def test_qss_exists():
    qss_path = os.path.join("src", "ui", "styles.qss")
    assert os.path.exists(qss_path)
    with open(qss_path, "r") as f:
        content = f.read()
        assert "QMainWindow" in content
        assert "#00F2FF" in content # Neon Blue

def test_main_initialization(qtbot):
    # This just ensures main() can run without crashing in a smoke test
    # We pass 0 as sys.exit expects it or main returns it.
    assert main() == 0
