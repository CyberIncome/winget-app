"""Explain WinGet version provenance without second-guessing upgrade authority.

WinGet's upgrade table may compare an installed Apps & Features ``DisplayVersion``
against a source manifest ``PackageVersion``. Those values can intentionally use
different numbering schemes. This module keeps both raw values, adds an optional
source-correlated installed package version from ``winget export
--include-versions``, and produces conservative presentation-only assessments.

Nothing here decides whether a package is upgradeable. Only the authoritative
WinGet upgrade scan may do that.
"""

from __future__ import annotations

import re


_NUMERIC_RE = re.compile(
    r"^\s*(?P<constraint><=|<|>=|>|=|~)?\s*[vV]?"
    r"(?P<version>\d+(?:\.\d+){0,7})\s*$"
)


def _numeric_version(value: object) -> tuple[tuple[int, ...], str] | None:
    text = str(value or "").strip()
    match = _NUMERIC_RE.fullmatch(text)
    if not match:
        return None
    numbers = tuple(int(part) for part in match.group("version").split("."))
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers = numbers[:-1]
    return numbers, (match.group("constraint") or "")


def _compare_numeric(left: object, right: object) -> int | None:
    parsed_left = _numeric_version(left)
    parsed_right = _numeric_version(right)
    if parsed_left is None or parsed_right is None:
        return None
    left, _left_constraint = parsed_left
    right, _right_constraint = parsed_right
    width = max(len(left), len(right))
    padded_left = left + (0,) * (width - len(left))
    padded_right = right + (0,) * (width - len(right))
    if padded_left == padded_right:
        return 0
    return -1 if padded_left < padded_right else 1


def assess_version_pair(
    installed_windows: object,
    target_winget: object,
    source_installed: object | None = None,
) -> dict[str, object]:
    """Return a conservative user-facing version relationship assessment."""
    windows = str(installed_windows or "").strip()
    target = str(target_winget or "").strip()
    source = str(source_installed or "").strip()

    if not target:
        return {
            "status": "missing-target",
            "needs_review": True,
            "summary": "WinGet did not provide a target package version.",
        }

    windows_numeric = _numeric_version(windows)
    source_numeric = _numeric_version(source) if source else None
    baseline = source if source else windows
    relation = _compare_numeric(baseline, target)
    mapping_differs = bool(source and windows and source.casefold() != windows.casefold())

    if source:
        if relation == -1:
            summary = (
                f"WinGet maps Windows version {windows or 'unknown'} to installed "
                f"package version {source}; target package version {target} is newer."
            )
            status = "mapped-upgrade"
        elif relation == 0:
            summary = (
                f"WinGet maps Windows version {windows or 'unknown'} to package "
                f"version {source}, which is equivalent to target {target}."
            )
            status = "mapped-equivalent"
        elif relation == 1:
            summary = (
                f"WinGet maps Windows version {windows or 'unknown'} to installed "
                f"package version {source}, which compares newer than target {target}."
            )
            status = "mapped-target-lower"
        else:
            summary = (
                f"Windows reports {windows or 'unknown'}; WinGet correlates the "
                f"installed package to {source}; target package version is {target}."
            )
            status = "mapped-incomparable"
        return {
            "status": status,
            "needs_review": mapping_differs or relation in {0, 1, None},
            "summary": summary,
            "mapping_differs": mapping_differs,
        }

    if windows_numeric is not None:
        _numbers, constraint = windows_numeric
        if constraint == "<" and relation in {-1, 0}:
            return {
                "status": "bounded-installed",
                "needs_review": False,
                "summary": (
                    f"Windows reports installed version {windows}; WinGet target "
                    f"package version is {target}. The installed value is a bound, "
                    "not an exact version."
                ),
            }

    if relation == -1:
        return {
            "status": "direct-upgrade",
            "needs_review": False,
            "summary": (
                f"Windows reports {windows}; WinGet target package version {target} "
                "compares newer in the same numeric scheme."
            ),
        }
    if relation == 0:
        return {
            "status": "equivalent",
            "needs_review": True,
            "summary": (
                f"Windows version {windows} and WinGet target {target} are numerically "
                "equivalent after normalizing trailing zeros. WinGet still reports "
                "this row as upgradeable, so its package/version mapping should be reviewed."
            ),
        }
    if relation == 1:
        return {
            "status": "target-lower",
            "needs_review": True,
            "summary": (
                f"Windows reports {windows}, while WinGet target package version {target} "
                "is numerically lower. This commonly indicates differing DisplayVersion "
                "and PackageVersion schemes rather than a literal downgrade."
            ),
        }

    return {
        "status": "different-scheme",
        "needs_review": True,
        "summary": (
            f"Windows reports {windows or 'unknown'} and WinGet target package version "
            f"is {target}. The values are not safely comparable as one numeric scheme."
        ),
    }


def annotate_version_row(row: dict) -> dict:
    """Return one row with presentation-only version provenance fields."""
    result = dict(row)
    assessment = assess_version_pair(
        result.get("Version"),
        result.get("Available"),
        result.get("SourceInstalledVersion"),
    )
    result["VersionStatus"] = assessment["status"]
    result["VersionNeedsReview"] = bool(assessment["needs_review"])
    result["VersionExplanation"] = str(assessment["summary"])
    return result


def extract_export_version_records(payload: object) -> list[dict[str, str]]:
    """Extract source-correlated installed package versions from WinGet export JSON."""
    if not isinstance(payload, dict):
        raise ValueError("WinGet export root must be an object")
    sources = payload.get("Sources")
    if not isinstance(sources, list):
        raise ValueError("WinGet export did not contain a Sources list")

    records: list[dict[str, str]] = []
    for source_entry in sources[:128]:
        if not isinstance(source_entry, dict):
            continue
        details = source_entry.get("SourceDetails")
        source_name = ""
        if isinstance(details, dict):
            source_name = str(details.get("Name") or "").strip()
        packages = source_entry.get("Packages")
        if not isinstance(packages, list):
            continue
        for package in packages[:20_000]:
            if not isinstance(package, dict):
                continue
            package_id = str(package.get("PackageIdentifier") or "").strip()
            version = str(package.get("Version") or "").strip()
            if not package_id or not version:
                continue
            records.append(
                {
                    "Id": package_id,
                    "Source": source_name,
                    "SourceInstalledVersion": version,
                }
            )
    return records


def merge_export_versions(rows: list[dict], records: list[dict]) -> list[dict]:
    """Attach exact source matches, with unique-ID fallback when source is absent."""
    exact: dict[tuple[str, str], str] = {}
    by_id: dict[str, list[str]] = {}
    for record in records or []:
        package_id = str(record.get("Id") or "").strip().casefold()
        source = str(record.get("Source") or "").strip().casefold()
        version = str(record.get("SourceInstalledVersion") or "").strip()
        if not package_id or not version:
            continue
        exact[(package_id, source)] = version
        by_id.setdefault(package_id, []).append(version)

    result = []
    for item in rows or []:
        row = dict(item)
        package_id = str(row.get("Id") or "").strip().casefold()
        source = str(row.get("Source") or "").strip().casefold()
        version = exact.get((package_id, source))
        if version is None and package_id:
            candidates = sorted(set(by_id.get(package_id, [])))
            if len(candidates) == 1:
                version = candidates[0]
        if version:
            row["SourceInstalledVersion"] = version
        result.append(annotate_version_row(row))
    return result
