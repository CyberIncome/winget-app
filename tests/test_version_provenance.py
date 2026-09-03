from src.logic.version_provenance import (
    annotate_version_row,
    assess_version_pair,
    extract_export_version_records,
    merge_export_versions,
)


def test_direct_numeric_upgrade_is_clear():
    result = assess_version_pair("0.100.2", "0.101.2362.0")
    assert result["status"] == "direct-upgrade"
    assert result["needs_review"] is False


def test_target_lower_is_mapping_warning_not_downgrade_authority():
    result = assess_version_pair("2.52.10.17731", "1.19.3.3219")
    assert result["status"] == "target-lower"
    assert result["needs_review"] is True
    assert "DisplayVersion" in result["summary"]


def test_trailing_zero_equivalence_requires_review():
    result = assess_version_pair("4.1.36.0", "4.1.36")
    assert result["status"] == "equivalent"
    assert result["needs_review"] is True


def test_less_than_installed_version_is_treated_as_bound():
    result = assess_version_pair("< 173.0.0.13316", "173.0.0.13316")
    assert result["status"] == "bounded-installed"
    assert result["needs_review"] is False


def test_source_correlated_package_version_explains_different_windows_scheme():
    result = assess_version_pair(
        "2.52.10.17731",
        "1.19.3.3219",
        "1.18.0.0",
    )
    assert result["status"] == "mapped-upgrade"
    assert result["needs_review"] is True
    assert "1.18.0.0" in result["summary"]


def test_non_numeric_schemes_are_not_guessed():
    result = assess_version_pair("1.0.98.2208_S13_R3", "1.0.108.2970")
    assert result["status"] == "different-scheme"
    assert result["needs_review"] is True


def test_extract_export_version_records_preserves_source_identity():
    payload = {
        "Sources": [
            {
                "SourceDetails": {"Name": "winget"},
                "Packages": [
                    {"PackageIdentifier": "Vendor.App", "Version": "1.2.3"},
                    {"PackageIdentifier": "No.Version"},
                ],
            },
            {
                "SourceDetails": {"Name": "private"},
                "Packages": [
                    {"PackageIdentifier": "Vendor.App", "Version": "9.9.9"},
                ],
            },
        ]
    }
    assert extract_export_version_records(payload) == [
        {"Id": "Vendor.App", "Source": "winget", "SourceInstalledVersion": "1.2.3"},
        {"Id": "Vendor.App", "Source": "private", "SourceInstalledVersion": "9.9.9"},
    ]


def test_merge_export_versions_uses_exact_id_and_source():
    rows = [
        {
            "Name": "Vendor App",
            "Id": "Vendor.App",
            "Version": "2026.4",
            "Available": "1.2.4",
            "Source": "winget",
        }
    ]
    records = [
        {"Id": "Vendor.App", "Source": "winget", "SourceInstalledVersion": "1.2.3"},
        {"Id": "Vendor.App", "Source": "private", "SourceInstalledVersion": "9.9.9"},
    ]
    merged = merge_export_versions(rows, records)
    assert merged[0]["SourceInstalledVersion"] == "1.2.3"
    assert merged[0]["VersionStatus"] == "mapped-upgrade"


def test_annotated_row_retains_original_raw_versions():
    row = annotate_version_row(
        {
            "Version": "2.0.7.0",
            "Available": "1.1",
            "Id": "CreativeTechnology.OpenAL",
        }
    )
    assert row["Version"] == "2.0.7.0"
    assert row["Available"] == "1.1"
    assert row["VersionNeedsReview"] is True
