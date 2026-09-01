"""Strict parsing helpers for ``winget upgrade`` table output.

WinGet does not currently expose structured JSON output for ``upgrade`` and
its human-readable labels are localized. This module therefore treats the
rendered table layout as an external protocol rather than requiring English
column names. Malformed output raises ``WingetParseError`` instead of being
silently reported as zero available updates.
"""

from __future__ import annotations

import re
import unicodedata
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
_HEADER_FIELD_RE = re.compile(r"\S(?:.*?\S)?(?=\s{2,}|$)")


def _clean_lines(output: str) -> list[str]:
    lines = []
    for raw in output.splitlines():
        clean = _ANSI_RE.sub("", raw).rstrip("\r\n")
        if clean.strip():
            lines.append(clean.strip())
    return lines


def _char_display_width(char: str) -> int:
    if char == "\t":
        return 4
    if unicodedata.combining(char):
        return 0
    if unicodedata.east_asian_width(char) in {"W", "F"}:
        return 2
    return 1


def _display_width(text: str) -> int:
    return sum(_char_display_width(char) for char in text)


def _index_at_display_column(text: str, target: int) -> int:
    """Return the string index whose terminal display column reaches target."""
    if target <= 0:
        return 0
    column = 0
    for index, char in enumerate(text):
        if column >= target:
            return index
        column += _char_display_width(char)
        if column > target:
            # A table formatter should never place a boundary inside a wide
            # glyph. Treat it as malformed rather than splitting the glyph.
            return -1
    return len(text) if column == target else -1


def _is_separator(line: str) -> bool:
    compact = line.replace(" ", "")
    return len(compact) >= 10 and bool(re.fullmatch(r"-+", compact))


def _header_layout(header: str) -> tuple[list[int], bool]:
    """Return localized column starts as terminal display columns."""
    stripped = header.strip()
    token_matches = list(re.finditer(r"\S+", stripped))
    if len(token_matches) in {4, 5}:
        matches = token_matches
    else:
        # Multiword translated labels use ordinary single spaces internally,
        # while table column padding normally contains two or more spaces.
        matches = list(_HEADER_FIELD_RE.finditer(stripped))
    if len(matches) not in {4, 5}:
        raise WingetParseError(
            "Winget upgrade table header did not expose a safe 4/5-column layout"
        )

    starts = [
        _display_width(stripped[: match.start()])
        for match in matches
    ]
    if starts != sorted(starts) or len(set(starts)) != len(starts):
        raise WingetParseError("Winget upgrade table columns are out of order")
    return starts, len(matches) == 5


def _plausible_package_id(value: str) -> bool:
    """Reject obvious version fields from being mistaken for the package ID."""
    value = value.strip()
    if not value or any(char.isspace() for char in value):
        return False
    if _VERSIONISH_RE.fullmatch(value):
        return False
    return any(char.isalnum() for char in value)


def _boundaries_are_aligned(line: str, indexes: list[int]) -> bool:
    """Ensure every calculated field start lands on an actual table boundary."""
    for index in indexes[1:]:
        if index <= 0 or index >= len(line):
            return False
        if not line[index - 1].isspace():
            return False
        if line[index].isspace():
            return False
    return True


def _slice_display_row(
    line: str,
    starts: list[int],
    has_source: bool,
) -> dict[str, str] | None:
    """Slice a row by terminal display columns, not Python codepoint offsets."""
    indexes = [_index_at_display_column(line, start) for start in starts]
    if any(index < 0 for index in indexes):
        return None
    if not _boundaries_are_aligned(line, indexes):
        return None

    # A row must actually reach the Available column. Source, when present in
    # the header, must also have at least one character at its column start.
    if _display_width(line) <= starts[3]:
        return None
    if has_source and _display_width(line) <= starts[4]:
        return None

    boundaries = [*indexes, len(line)]
    fields = [
        line[boundaries[index] : boundaries[index + 1]].strip()
        for index in range(len(starts))
    ]
    if len(fields) not in {4, 5}:
        return None

    name, package_id, version, available = fields[:4]
    source = fields[4] if has_source else ""
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

    WinGet's labels are localized, but the table remains an ordered four-column
    layout (Name, Id, Version, Available) with an optional fifth Source column.
    Column positions are measured in terminal display cells so CJK/full-width
    text cannot shift Python slicing offsets.

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
    starts = None
    has_source = False

    for index in range(1, len(lines)):
        if not _is_separator(lines[index]):
            continue
        separator_index = index
        starts, has_source = _header_layout(lines[index - 1])
        break

    if separator_index is None or starts is None:
        raise WingetParseError(
            "Winget output did not contain a recognizable upgrade table "
            "or no-update marker"
        )

    rows: list[dict[str, str]] = []
    malformed_data_lines = 0

    for line in lines[separator_index + 1 :]:
        row = _slice_display_row(line, starts, has_source)
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
