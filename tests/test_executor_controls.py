import pytest

from src.logic.executor import (
    is_valid_app_id,
    validate_app_id,
    validate_package_name,
    validate_source_name,
)


@pytest.mark.parametrize(
    "value",
    [
        "Google.Chrome\n",
        "Google.Chrome\r",
        "Google.Chrome\x00",
        "Google.Chrome\t",
        "Google.Chrome\x1b",
        "Google.Chrome\x7f",
        "Google.Chrome\nOther.App",
        "--help",
        "-Example.App",
    ],
)
def test_app_id_rejects_unsafe_values(value):
    assert is_valid_app_id(value) is False
    with pytest.raises(ValueError):
        validate_app_id(value)


@pytest.mark.parametrize(
    "validator,value",
    [
        (validate_package_name, "App\n"),
        (validate_package_name, "\nApp"),
        (validate_package_name, "App\x00Name"),
        (validate_package_name, "App\tName"),
        (validate_package_name, "App\x1bName"),
        (validate_package_name, "App\x7fName"),
        (validate_source_name, "winget\n"),
        (validate_source_name, "\nwinget"),
        (validate_source_name, "winget\x00evil"),
        (validate_source_name, "winget\tother"),
        (validate_source_name, "winget\x1bother"),
        (validate_source_name, "winget\x7fother"),
    ],
)
def test_name_and_source_reject_control_characters(validator, value):
    with pytest.raises(ValueError):
        validator(value)
