import pytest

from src.logic.executor import WingetExecutor, validate_package_version


def test_exact_target_update_command_includes_version_and_source():
    command = WingetExecutor().get_update_cmd(
        "Vendor.App",
        source="winget",
        version="2.4.1",
    )
    assert command == [
        "winget",
        "upgrade",
        "--id",
        "Vendor.App",
        "--exact",
        "--source",
        "winget",
        "--version",
        "2.4.1",
        "--silent",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]


def test_exact_target_show_command_uses_same_version():
    command = WingetExecutor().get_show_cmd(
        "Vendor.App",
        source="winget",
        version="2.4.1",
    )
    assert command == [
        "winget",
        "show",
        "--id",
        "Vendor.App",
        "--exact",
        "--source",
        "winget",
        "--version",
        "2.4.1",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]


def test_package_version_validation_is_single_argument_safe():
    assert validate_package_version("1.0.98.2208_S13_R3") == "1.0.98.2208_S13_R3"
    assert validate_package_version(" 2026.8.2 ") == "2026.8.2"
    assert validate_package_version(None) == ""
    with pytest.raises(ValueError):
        validate_package_version("--force")
    with pytest.raises(ValueError):
        validate_package_version("1.2.3\n--force")
