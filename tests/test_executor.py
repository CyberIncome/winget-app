import pytest

from src.logic.executor import (
    WingetExecutor,
    is_valid_app_id,
    validate_app_id,
    validate_package_name,
    validate_source_name,
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


def test_generate_update_with_source_cmd():
    executor = WingetExecutor()
    cmd = executor.get_update_cmd(
        "Contoso.App",
        source="private-feed",
    )
    assert cmd == [
        "winget",
        "upgrade",
        "--id",
        "Contoso.App",
        "--exact",
        "--source",
        "private-feed",
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


def test_is_valid_app_id_rejects_display_truncation():
    assert is_valid_app_id("Google.Chrome") is True
    assert (
        is_valid_app_id("Microsoft.VisualStudio.2022.BuildToo...")
        is False
    )
    assert (
        is_valid_app_id("Microsoft.VisualStudio.2022.BuildToo\u2026")
        is False
    )
    assert is_valid_app_id("Vendor.Package.") is False
    assert is_valid_app_id("Visual Studio Code") is False


@pytest.mark.parametrize(
    "truncated",
    [
        "Microsoft.VisualStudio.2022.BuildToo...",
        "Vendor.Package.",
    ],
)
def test_validate_app_id_rejects_trailing_dot(truncated):
    with pytest.raises(ValueError):
        validate_app_id(truncated)


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


def test_package_name_and_source_reject_option_like_values():
    with pytest.raises(ValueError):
        validate_package_name("--all")
    with pytest.raises(ValueError):
        validate_source_name("--source")


def test_source_validation_allows_normal_names_and_empty():
    assert validate_source_name("winget") == "winget"
    assert validate_source_name("private-feed") == "private-feed"
    assert validate_source_name("") == ""
    assert validate_source_name(None) == ""