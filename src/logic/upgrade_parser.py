"""Strict parsing helpers for ``winget upgrade`` table output.

WinGet does not currently expose structured JSON output for ``upgrade``. This
module therefore treats the human-readable table as an external protocol: the
header and required column boundaries must be validated before any row is
accepted. Malformed output raises ``WingetParseError`` instead of being
silently reported as zero available updates.
"""

from __future__ import annotations

import re
from typing import Iterable


class WingetParseError(ValueError):
    """Raised when Winget output cannot be safely interpreted as an upgrade table."""


_REQUIRED_COLUMNS = ("Name", "Id", "Version", "Available")
_OPTIONAL_COLUMNS = ("Source",)
_NO_UPDATE_MARKERS = (
    "no applicable update found",
    "no installed package found matching input criteria",
)
_TRAILER_RE = re.compile(r"^\d+\s+(?:upgrades?|packages?)\s+", re.IGNORECASE)
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _clean_lines(output: str) -> list[str]:
    lines = []
    for raw in output.splitlines():
        clean = _ANSI_RE.sub("", raw).rstrip("\r\n")
        if clean.strip():
            lines.append(clean.strip())
    return lines


def _column_starts(header: str) -> dict[str, int]:
    starts: dict[str, int] = {}
    for name in (*_REQUIRED_COLUMNS, *_OPTIONAL_COLUMNS):
        match = re.search(rf"(?<!\S){re.escape(name)}(?!\S)", header)
        if match:
            starts[name] = match.start()

    missing = [name for name in _REQUIRED_COLUMNS if name not in starts]
    if missing:
        raise WingetParseError(
            "Winget upgrade table is missing required column(s): "
            + ", ".join(missing)
        )

    required_positions = [starts[name] for name in _REQUIRED_COLUMNS]
    if required_positions != sorted(required_positions) or len(
        set(required_positions)
    ) != len(required_positions):
        raise WingetParseError("Winget upgrade table columns are out of order")

    if "Source" in starts and starts["Source"] <= starts["Available"]:
        raise WingetParseError("Winget upgrade table Source column is out of order")
    return starts


def _slice_row(line: str, starts: dict[str, int]) -> dict[str, str]:
    order = [
        name
        for name in (*_REQUIRED_COLUMNS, *_OPTIONAL_COLUMNS)
        if name in starts
    ]
    row: dict[str, str] = {}
    for index, name in enumerate(order):
        start = starts[name]
        end = starts[order[index + 1]] if index + 1 < len(order) else len(line)
        row[name] = line[start:end].strip() if start < len(line) else ""
    return row


def parse_upgrade_table(output: str) -> list[dict[str, str]]:
    """Parse validated rows from ``winget upgrade`` output.

    ``Source`` is optional because WinGet output can omit it depending on source
    configuration/version. The returned row always contains a ``Source`` key;
    it is an empty string when the column is absent. Any malformed package row
    fails the whole parse so a partial/truncated table cannot silently hide
    updates.
    """
    if not output or not output.strip():
        return []

    lowered = output.lower()
    if any(marker in lowered for marker in _NO_UPDATE_MARKERS):
        return []

    lines = _clean_lines(output)
    header_index = None
    separator_index = None
    starts: dict[str, int] | None = None

    for index, line in enumerate(lines):
        if all(
            re.search(rf"\b{re.escape(col)}\b", line)
            for col in _REQUIRED_COLUMNS
        ):
            candidate_starts = _column_starts(line)
            if index + 1 >= len(lines) or not re.fullmatch(
                r"[-\s]+", lines[index + 1]
            ):
                raise WingetParseError(
                    "Winget upgrade table header has no separator row"
                )
            header_index = index
            separator_index = index + 1
            starts = candidate_starts
            break

    if header_index is None or separator_index is None or starts is None:
        raise WingetParseError(
            "Winget output did not contain a recognizable upgrade table "
            "or no-update marker"
        )

    rows: list[dict[str, str]] = []
    malformed_data_lines = 0
    min_data_width = starts["Available"] + 1

    for line in lines[separator_index + 1 :]:
        stripped = line.strip()
        if _TRAILER_RE.match(stripped):
            break
        if stripped.startswith(
            ("-", "The following", "Some packages", "Pinning")
        ):
            continue

        if len(line) < min_data_width:
            if any(char.isalnum() for char in line):
                malformed_data_lines += 1
            continue

        row = _slice_row(line, starts)
        if not row.get("Name") and not row.get("Id"):
            continue
        if not row.get("Name") or not row.get("Id"):
            malformed_data_lines += 1
            continue
        if not row.get("Version") or not row.get("Available"):
            malformed_data_lines += 1
            continue

        rows.append(
            {
                **{name: row.get(name, "") for name in _REQUIRED_COLUMNS},
                "Source": row.get("Source", ""),
            }
        )

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
    """Apply the existing registry/version heuristics to already parsed rows."""
    from src.logic.parser import (
        find_version_in_registry,
        is_version_newer,
        parse_version_tuple,
    )

    materialized = [dict(row) for row in rows]
    if reg_data is None:
        from src.logic.parser import get_registry_data

        reg_data = get_registry_data()

    results: list[dict[str, str]] = []
    for row in materialized:
        reported_version = row["Version"]
        displayed_version = reported_version
        if reported_version.strip().lower() == "unknown":
            detected = find_version_in_registry(
                row["Name"], row["Id"], reg_data, allow_fuzzy=False
            )
            if detected:
                displayed_version = detected
                row["Version"] = detected

        uncertain = (
            not reported_version
            or reported_version.strip().lower() in {"unknown", "???"}
            or any(token in reported_version for token in ("<", ">", "~"))
        )
        if (
            not uncertain
            and parse_version_tuple(displayed_version) is not None
            and row.get("Available")
            and not is_version_newer(row["Available"], displayed_version)
        ):
            continue
        results.append(row)

    results.sort(
        key=lambda item: (
            item["Version"].lower() != "unknown",
            item["Name"].lower(),
        )
    )
    return results


def parse_winget_upgrade_strict(
    output: str, reg_data: list[dict] | None = None
) -> list[dict[str, str]]:
    """Parse and enrich a Winget upgrade table with explicit failure semantics."""
    return enrich_upgrade_rows(parse_upgrade_table(output), reg_data=reg_data)
