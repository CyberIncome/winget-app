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
        "Google.Chrome\nOther.App",
    ],
)
def test_app_id_rejects_control_characters(value):
    assert is_valid_app_id(value) is False
    with pytest.raises(ValueError):
        validate_app_id(value)


@pytest.mark.parametrize(
    "validator,value",
    [
        (validate_package_name, "App\n"),
        (validate_package_name, "\nApp"),
        (validate_package_name, "App\x00Name"),
        (validate_source_name, "winget\n"),
        (validate_source_name, "\nwinget"),
        (validate_source_name, "winget\x00evil"),
    ],
)
def test_name_and_source_reject_control_characters(validator, value):
    with pytest.raises(ValueError):
        validator(value)
