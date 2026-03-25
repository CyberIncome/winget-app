import pytest
from src.logic.executor import WingetExecutor, validate_app_id


def test_generate_upgrade_command():
    executor = WingetExecutor()
    assert executor.get_check_updates_cmd() == [
        "winget", "upgrade", "--include-unknown"
    ]


def test_generate_update_single_cmd():
    executor = WingetExecutor()
    cmd = executor.get_update_cmd("Google.Chrome")
    assert cmd == [
        "winget", "upgrade", "--id", "Google.Chrome",
        "--silent", "--accept-package-agreements",
        "--accept-source-agreements",
    ]


def test_generate_update_all_cmd():
    executor = WingetExecutor()
    cmd = executor.get_update_all_cmd()
    assert cmd == [
        "winget", "upgrade", "--all",
        "--include-unknown", "--silent",
        "--accept-package-agreements",
        "--accept-source-agreements",
    ]


# --- C1: app_id validation tests ---

def test_validate_app_id_valid():
    assert validate_app_id("Google.Chrome") == "Google.Chrome"
    assert validate_app_id("7zip.7zip") == "7zip.7zip"
    assert validate_app_id("App-Name_1.0") == "App-Name_1.0"


def test_validate_app_id_rejects_injection():
    """Crafted IDs with arguments must be rejected."""
    with pytest.raises(ValueError):
        validate_app_id("Foo --force")
    with pytest.raises(ValueError):
        validate_app_id('Foo; rm -rf /')
    with pytest.raises(ValueError):
        validate_app_id("Foo --override C:\\Windows")


def test_validate_app_id_rejects_empty():
    with pytest.raises(ValueError):
        validate_app_id("")
    with pytest.raises(ValueError):
        validate_app_id(None)
