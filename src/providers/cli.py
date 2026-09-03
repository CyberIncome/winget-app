"""Read-only developer CLI for the additive provider layer.

This module intentionally exposes probe/scan only. Provider execution will not
be wired into the public CLI or GUI until provider-owned action dispatch has its
own process-lifecycle and confirmation tests.
"""

from __future__ import annotations

import argparse
import json

from src.providers.defaults import build_default_provider_registry


def _status_rows(registry) -> list[dict]:
    return [status.to_dict() for status in registry.probe_all()]


def _scan_rows(registry, provider_ids: list[str] | None) -> list[dict]:
    return [result.to_dict() for result in registry.scan_all(provider_ids)]


def _print_status(rows: list[dict]) -> None:
    for row in rows:
        availability = "ready" if row["available"] else "not available"
        if row["available"] and row.get("requires_opt_in"):
            availability = "ready (opt-in)"
        version = f" {row['version']}" if row.get("version") else ""
        print(
            f"{row['display_name']:<24} {availability:<18} "
            f"{row['mode']:<13}{version}"
        )
        if row.get("reason"):
            print(f"  {row['reason']}")


def _print_scan(rows: list[dict]) -> None:
    total = 0
    for result in rows:
        status = result["status"]
        print(f"\n[{status['display_name']}] {status['mode']}")
        if not status["available"]:
            print(f"  unavailable: {status.get('reason') or 'not detected'}")
            continue
        if result.get("error"):
            print(f"  ERROR: {result['error']}")
            continue
        updates = result.get("updates") or []
        warnings = result.get("warnings") or []
        total += len(updates)
        opt_in_skipped = (
            status.get("requires_opt_in")
            and not updates
            and any("explicit opt-in" in warning for warning in warnings)
        )
        if opt_in_skipped:
            print("  not scanned: explicit opt-in required")
        elif not updates:
            print("  no updates reported")
        for update in updates:
            target = update.get("available_version") or "unknown"
            current = update.get("installed_version") or "unknown"
            action = "managed" if update.get("can_update") else update.get("mode")
            print(
                f"  {update['name']}: {current} -> {target} "
                f"({action})"
            )
            if update.get("blocked_reason"):
                print(f"    {update['blocked_reason']}")
        for warning in warnings:
            print(f"  warning: {warning}")
    print(f"\nProvider updates reported: {total}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe and scan additive update providers."
    )
    parser.add_argument(
        "command",
        choices=("status", "scan"),
        help="Probe provider availability or perform read-only update scans.",
    )
    parser.add_argument(
        "--provider",
        action="append",
        default=None,
        help=(
            "Provider id to scan. Repeat to select multiple providers. "
            "Explicit selection opts into providers that may use an account."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    registry = build_default_provider_registry()
    if args.command == "status":
        rows = _status_rows(registry)
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            _print_status(rows)
        return 0

    rows = _scan_rows(registry, args.provider)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        _print_scan(rows)
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
