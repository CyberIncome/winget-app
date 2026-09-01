import pytest

from src.logic.executor import (
    WingetExecutor,
    is_valid_app_id,
    validate_app_id,
)


def test_generate_upgrade_command():
    executor = WingetExecutor()
    assert executor.get_check_updates_cmd() == [
        "winget",
        "upgrade",
        "--include-unknown",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]


def test_generate_update_single_cmd():
    executor = WingetExecutor()
    cmd = executor.get_update_cmd("Google.Chrome")
    assert cmd == [
        "winget",
        "upgrade",
        "--id",
        "Google.Chrome",
        "--exact",
        "--silent",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]


def test_generate_update_by_name_cmd():
    executor = WingetExecutor()
    cmd = executor.get_update_cmd(
        "Visual Studio Build Tools 2022", match_by="name"
    )
    assert cmd == [
        "winget",
        "upgrade",
        "--name",
        "Visual Studio Build Tools 2022",
        "--exact",
        "--silent",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]


def test_generate_update_without_silent_cmd():
    executor = WingetExecutor()
    cmd = executor.get_update_cmd(
        "Perplexity.Comet", silent=False
    )
    assert cmd == [
        "winget",
        "upgrade",
        "--id",
        "Perplexity.Comet",
        "--exact",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]


def test_generate_update_all_cmd():
    executor = WingetExecutor()
    assert executor.get_update_all_cmd() == [
        "winget",
        "upgrade",
        "--all",
        "--include-unknown",
        "--silent",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]


def test_validate_app_id_valid():
    assert validate_app_id("Google.Chrome") == "Google.Chrome"
    assert validate_app_id("7zip.7zip") == "7zip.7zip"
    assert validate_app_id("App-Name_1.0") == "App-Name_1.0"


def test_is_valid_app_id():
    assert is_valid_app_id("Google.Chrome") is True
    assert is_valid_app_id(
        "Microsoft.VisualStudio.2022.BuildToo..."
    ) is True
    assert (
        is_valid_app_id("Microsoft.VisualStudio.2022.BuildToo\u2026")
        is False
    )
    assert is_valid_app_id("Visual Studio Code") is False


def test_validate_app_id_rejects_injection():
    with pytest.raises(ValueError):
        validate_app_id("Foo --force")
    with pytest.raises(ValueError):
        validate_app_id("Foo; rm -rf /")
    with pytest.raises(ValueError):
        validate_app_id("Foo --override C:\\Windows")


def test_validate_app_id_rejects_empty():
    with pytest.raises(ValueError):
        validate_app_id("")
    with pytest.raises(ValueError):
        validate_app_id(None)
