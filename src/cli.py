"""Command-line interface for Winget Universal Dashboard."""

from __future__ import annotations

import json
import logging
import subprocess
import time

import click

from src.app_info import APP_NAME, get_app_version
from src.logic.command_runner import CommandResult, run_command
from src.logic.executor import (
    WingetExecutor,
    validate_app_id,
    validate_package_version,
    validate_source_name,
)
from src.logic.upgrade_parser import WingetParseError, parse_winget_upgrade_strict
from src.logic.version_provenance import annotate_version_row


def setup_logging(verbose):
    """Configure CLI logging."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )


def run_winget(args, timeout=300) -> CommandResult:
    """Run a Winget argument list with structured failure state."""
    command = ["winget", *args]
    logging.debug("Running: %s", " ".join(command))
    return run_command(command, timeout=timeout)


def run_upgrade_scan(timeout=300) -> CommandResult:
    """Run the same non-interactive update scan used by the GUI."""
    command = WingetExecutor().get_check_updates_cmd()
    logging.debug("Running: %s", " ".join(command))
    return run_command(command, timeout=timeout)


def _require_success(result: CommandResult) -> str:
    if result.ok:
        return result.stdout
    raise click.ClickException(f"winget {result.failure_summary()}")


def print_table(rows, columns, widths=None):
    """Print a formatted table."""
    if not rows:
        click.echo("  (no results)")
        return

    if widths is None:
        widths = {}
        for column in columns:
            max_width = max(
                [len(column)]
                + [len(str(row.get(column, ""))) for row in rows]
            )
            widths[column] = min(max_width + 2, 50)

    header = "".join(str(column).ljust(widths[column]) for column in columns)
    click.secho(header, fg="cyan", bold=True)
    click.echo("─" * sum(widths.values()))

    for row in rows:
        parts = []
        for column in columns:
            value = str(row.get(column, ""))
            if len(value) > widths[column] - 2:
                value = value[: widths[column] - 5] + "..."
            parts.append(value.ljust(widths[column]))
        line = "".join(parts)
        version = str(row.get("Version", "")).lower()
        if "unknown" in version or "???" in version:
            click.secho(line, fg="yellow")
        elif row.get("Available") or row.get("Target (WinGet)"):
            click.secho(line, fg="green")
        else:
            click.echo(line)


def output_json(data):
    """Emit machine-readable JSON to stdout."""
    click.echo(json.dumps(data, indent=2, default=str))


def _progress(ctx, text, color="blue"):
    if not ctx.obj.get("json"):
        click.secho(text, fg=color)


@click.group()
@click.version_option(version=get_app_version(), prog_name=APP_NAME)
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
@click.option(
    "--json-output",
    "use_json",
    is_flag=True,
    help="Output results as JSON.",
)
@click.pass_context
def cli(ctx, verbose, use_json):
    """Manage Windows packages from the command line."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = use_json
    ctx.obj["verbose"] = verbose
    setup_logging(verbose)


@cli.command()
@click.pass_context
def check(ctx):
    """Check for available updates via Winget."""
    _progress(ctx, "Checking for updates...")
    from src.logic.parser import get_registry_data

    reg_data = get_registry_data()
    output = _require_success(run_upgrade_scan())
    try:
        parsed = parse_winget_upgrade_strict(output, reg_data=reg_data)
    except WingetParseError as exc:
        raise click.ClickException(
            f"could not parse winget upgrade output safely: {exc}"
        ) from exc

    results = [annotate_version_row(dict(item)) for item in parsed]
    if ctx.obj["json"]:
        output_json(results)
        return

    click.secho(
        f"\n{len(results)} updates available\n",
        fg="green",
        bold=True,
    )
    display_rows = [
        {
            "Name": row.get("Name", ""),
            "Id": row.get("Id", ""),
            "Installed (Windows)": row.get("Version", ""),
            "Target (WinGet)": row.get("Available", ""),
            "Version Status": row.get("VersionStatus", ""),
            "Source": row.get("Source", ""),
        }
        for row in results
    ]
    print_table(
        display_rows,
        [
            "Name",
            "Id",
            "Installed (Windows)",
            "Target (WinGet)",
            "Version Status",
            "Source",
        ],
    )
    review_count = sum(bool(row.get("VersionNeedsReview")) for row in results)
    if review_count:
        click.secho(
            (
                f"\n{review_count} row(s) use version values that do not compare "
                "cleanly between Windows DisplayVersion and WinGet PackageVersion. "
                "They remain WinGet-reported upgrades; use --json-output for the "
                "full provenance explanation."
            ),
            fg="yellow",
        )


@cli.command()
@click.option(
    "--type",
    "app_type",
    type=click.Choice(
        ["all", "installed", "portable"], case_sensitive=False
    ),
    default="all",
    help="Filter by app type.",
)
@click.pass_context
def inventory(ctx, app_type):
    """Scan full system inventory (registry + shortcuts)."""
    _progress(ctx, "Scanning system inventory...")
    from src.logic.parser import get_total_inventory

    started = time.monotonic()
    data = get_total_inventory()
    elapsed = time.monotonic() - started
    if app_type != "all":
        target = "Installed" if app_type == "installed" else "Portable"
        data = [item for item in data if item.get("Type") == target]

    if ctx.obj["json"]:
        output_json(data)
        return
    click.secho(
        f"\n{len(data)} applications found ({elapsed:.1f}s)\n",
        fg="green",
        bold=True,
    )
    print_table(data, ["Name", "Version", "Type", "Managed"])


@cli.command()
@click.argument("app_id", required=False)
@click.option(
    "--all", "update_all", is_flag=True, help="Update all available packages."
)
@click.option(
    "--source",
    help=(
        "Winget source for one exact package update; useful when the same "
        "package ID exists in multiple configured sources."
    ),
)
@click.option(
    "--version",
    "target_version",
    help=(
        "Exact WinGet package version for one package. Omit to let WinGet "
        "select the current latest version."
    ),
)
@click.pass_context
def update(ctx, app_id, update_all, source, target_version):
    """Update a specific app or all apps."""
    executor = WingetExecutor()
    if update_all:
        if source or target_version:
            raise click.UsageError(
                "--source and --version apply only to a specific app update, not --all"
            )
        _progress(ctx, "Updating all packages...", "green")
        _run_update_live(executor.get_update_all_cmd())
        return

    if not app_id:
        raise click.UsageError("provide an app ID or use --all")
    try:
        validate_app_id(app_id)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="app_id") from exc
    try:
        source = validate_source_name(source)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="--source") from exc
    try:
        target_version = validate_package_version(target_version)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="--version") from exc

    suffix = f" to {target_version}" if target_version else ""
    _progress(ctx, f"Updating {app_id}{suffix}...", "green")
    _run_update_live(
        executor.get_update_cmd(
            app_id,
            source=source or None,
            version=target_version or None,
        )
    )


def _run_update_live(command):
    """Run an update with live merged stdout/stderr and bounded cancellation."""
    process = None
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if process.stdout is not None:
            for line in process.stdout:
                click.echo(f"  {line}", nl=False)
        return_code = process.wait()
    except KeyboardInterrupt as exc:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        raise click.Abort() from exc
    except OSError as exc:
        raise click.ClickException(
            f"winget failed to start: {exc}"
        ) from exc

    if return_code != 0:
        raise click.ClickException(
            f"winget exited with code {return_code}"
        )
