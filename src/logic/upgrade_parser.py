"""Strict parsing helpers for ``winget upgrade`` table output.

WinGet does not currently expose structured JSON output for ``upgrade`` and
its human-readable labels are localized. This module therefore treats the
rendered table layout as an external protocol rather than requiring English
column names. Malformed output raises ``WingetParseError`` instead of being
silently reported as zero available updates.
"""

from __future__ import annotations

import re
from typing import Iterable


class WingetParseError(ValueError):
    """Raised when Winget output cannot be safely interpreted as an upgrade table."""


_REQUIRED_COLUMNS = ("Name", "Id", "Version", "Available")
_NO_UPDATE_MARKERS = (
    "no applicable update found",
    "no installed package found matching input criteria",
)
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_VERSIONISH_RE = re.compile(
    r"^(?:[<>~=]{1,2}\s*)?(?:v?\d+(?:\.\d+)*|unknown|\?\?\?)$",
    re.IGNORECASE,
)


def _clean_lines(output: str) -> list[str]:
    lines = []
    for raw in output.splitlines():
        clean = _ANSI_RE.sub("", raw).rstrip("\r\n")
        if clean.strip():
            lines.append(clean.strip())
    return lines


def _is_separator(line: str) -> bool:
    compact = line.replace(" ", "")
    return len(compact) >= 10 and bool(re.fullmatch(r"-+", compact))


def _header_has_source(header: str) -> bool:
    """Infer the stable 4/5-column table shape without reading localized labels."""
    fields = [
        field.strip()
        for field in re.split(r"\s{2,}", header.strip())
        if field.strip()
    ]
    if len(fields) == 4:
        return False
    if len(fields) == 5:
        return True
    raise WingetParseError(
        "Winget upgrade table header did not expose a safe 4/5-column layout"
    )


def _plausible_package_id(value: str) -> bool:
    """Reject obvious version fields from being mistaken for the package ID."""
    value = value.strip()
    if not value or any(char.isspace() for char in value):
        return False
    if _VERSIONISH_RE.fullmatch(value):
        return False
    return any(char.isalnum() for char in value)


def _parse_layout_row(line: str, has_source: bool) -> dict[str, str] | None:
    """Parse one row from the right, avoiding Unicode display-width offsets.

    WinGet aligns columns by terminal display width, which does not equal
    Python string length for CJK/full-width names. We therefore split on the
    table's padding runs from the right. The final prefix contains ``Name`` and
    ``Id``; the ID is the last whitespace-delimited token in that prefix.
    """
    parts = [part.strip() for part in re.split(r"\s{2,}", line.strip())]
    minimum_parts = 4 if has_source else 3
    if len(parts) < minimum_parts:
        return None

    if has_source:
        source = parts[-1]
        available = parts[-2]
        version = parts[-3]
        prefix_parts = parts[:-3]
    else:
        source = ""
        available = parts[-1]
        version = parts[-2]
        prefix_parts = parts[:-2]

    prefix = "  ".join(prefix_parts).strip()
    try:
        name, package_id = prefix.rsplit(None, 1)
    except ValueError:
        return None

    name = name.strip()
    package_id = package_id.strip()
    version = version.strip()
    available = available.strip()
    source = source.strip()

    if not name or not _plausible_package_id(package_id):
        return None
    if not version or not available:
        return None
    if has_source and not source:
        return None

    return {
        "Name": name,
        "Id": package_id,
        "Version": version,
        "Available": available,
        "Source": source,
    }


def _looks_like_localized_summary(line: str) -> bool:
    """Recognize a compact count-summary after at least one parsed row."""
    stripped = line.strip()
    return bool(
        re.match(r"^\d+\s+", stripped)
        and not re.search(r"\s{2,}", stripped)
    )


def parse_upgrade_table(output: str) -> list[dict[str, str]]:
    """Parse validated rows from localized ``winget upgrade`` output.

    WinGet's column labels are localized, but the table remains an ordered
    four-column layout (Name, Id, Version, Available) with an optional fifth
    Source column. Parsing is structural and right-anchored so full-width
    characters in application names cannot shift Python slicing offsets.

    Any malformed package row fails the whole parse so partial/truncated output
    cannot silently hide updates. Empty/whitespace-only output is also an error:
    only an explicit recognized no-update marker may authoritatively mean zero
    updates.
    """
    if not output or not output.strip():
        raise WingetParseError(
            "Winget upgrade produced empty output without a no-update marker"
        )

    lowered = output.lower()
    if any(marker in lowered for marker in _NO_UPDATE_MARKERS):
        return []

    lines = _clean_lines(output)
    separator_index = None
    has_source = None

    for index in range(1, len(lines)):
        if not _is_separator(lines[index]):
            continue
        separator_index = index
        has_source = _header_has_source(lines[index - 1])
        break

    if separator_index is None or has_source is None:
        raise WingetParseError(
            "Winget output did not contain a recognizable upgrade table "
            "or no-update marker"
        )

    rows: list[dict[str, str]] = []
    malformed_data_lines = 0

    for line in lines[separator_index + 1 :]:
        row = _parse_layout_row(line, has_source)
        if row is not None:
            rows.append(row)
            continue

        stripped = line.strip()
        if rows and _looks_like_localized_summary(stripped):
            break
        if stripped.startswith(
            ("-", "The following", "Some packages", "Pinning")
        ):
            continue
        if any(char.isalnum() for char in stripped):
            malformed_data_lines += 1

    if malformed_data_lines:
        raise WingetParseError(
            "Winget upgrade table contained "
            f"{malformed_data_lines} malformed data row(s)"
        )
    if not rows:
        raise WingetParseError(
            "Winget upgrade table contained no package rows and no "
            "recognized no-update marker"
        )
    return rows


def enrich_upgrade_rows(
    rows: Iterable[dict[str, str]], reg_data: list[dict] | None = None
) -> list[dict[str, str]]:
    """Enrich installed versions without overruling Winget upgrade authority.

    Rows in this function have already been emitted by ``winget upgrade``. The
    package manager therefore remains authoritative about whether an upgrade is
    available. Local registry heuristics may replace an ``unknown`` installed
    version for display, but must never discard a Winget row based on our much
    simpler numeric version parser.
    """
    materialized = [dict(row) for row in rows]
    unknown_rows = [
        row
        for row in materialized
        if row["Version"].strip().lower() == "unknown"
    ]

    if unknown_rows:
        from src.logic.parser import find_version_in_registry

        if reg_data is None:
            from src.logic.parser import get_registry_data

            reg_data = get_registry_data()

        for row in unknown_rows:
            detected = find_version_in_registry(
                row["Name"], row["Id"], reg_data, allow_fuzzy=False
            )
            if detected:
                row["Version"] = detected

    materialized.sort(
        key=lambda item: (
            item["Version"].lower() != "unknown",
            item["Name"].lower(),
        )
    )
    return materialized


def parse_winget_upgrade_strict(
    output: str, reg_data: list[dict] | None = None
) -> list[dict[str, str]]:
    """Parse and enrich a Winget upgrade table with explicit failure semantics."""
    return enrich_upgrade_rows(parse_upgrade_table(output), reg_data=reg_data)
