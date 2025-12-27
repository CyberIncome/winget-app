import pytest
from src.logic.executor import WingetExecutor

def test_generate_upgrade_command():
    executor = WingetExecutor()
    # Test checking for upgrades
    assert executor.get_check_updates_cmd() == ["winget", "upgrade", "--include-unknown"]

def test_generate_update_single_cmd():
    executor = WingetExecutor()
    # Test updating a single app by ID
    cmd = executor.get_update_cmd("Google.Chrome")
    assert cmd == ["winget", "upgrade", "--id", "Google.Chrome", "--silent", "--accept-package-agreements", "--accept-source-agreements"]

def test_generate_update_all_cmd():
    executor = WingetExecutor()
    # Test updating all apps
    cmd = executor.get_update_all_cmd()
    assert cmd == ["winget", "upgrade", "--all", "--include-unknown", "--silent", "--accept-package-agreements", "--accept-source-agreements"]
