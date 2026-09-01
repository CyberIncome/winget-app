"""Command-line interface for Winget Universal Dashboard."""

from __future__ import annotations

import json
import logging
import subprocess
import time

import click

from src.logic.command_runner import CommandResult, run_command
from src.logic.executor import WingetExecutor, validate_app_id
from src.logic.upgrade_parser import WingetParseError, parse_winget_upgrade_strict


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
        elif row.get("Available"):
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
        results = parse_winget_upgrade_strict(
            output, reg_data=reg_data
        )
    except WingetParseError as exc:
        raise click.ClickException(
            f"could not parse winget upgrade output safely: {exc}"
        ) from exc

    if ctx.obj["json"]:
        output_json(results)
        return

    click.secho(
        f"\n{len(results)} updates available\n",
        fg="green",
        bold=True,
    )
    print_table(
        results,
        ["Name", "Id", "Version", "Available", "Source"],
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
@click.pass_context
def update(ctx, app_id, update_all):
    """Update a specific app or all apps."""
    executor = WingetExecutor()
    if update_all:
        _progress(ctx, "Updating all packages...", "green")
        _run_update_live(executor.get_update_all_cmd())
        return

    if not app_id:
        raise click.UsageError("provide an app ID or use --all")
    try:
        validate_app_id(app_id)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="app_id") from exc

    _progress(ctx, f"Updating {app_id}...", "green")
    _run_update_live(executor.get_update_cmd(app_id))


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
    click.secho("\nUpdate complete.", fg="green")


@cli.command()
@click.argument("query")
@click.pass_context
def search(ctx, query):
    """Search installed applications by name or ID."""
    _progress(ctx, f"Searching for {query!r}...")
    from src.logic.parser import get_total_inventory

    query_lower = query.lower()
    data = get_total_inventory()
    matches = [
        item
        for item in data
        if query_lower in item.get("Name", "").lower()
        or query_lower in item.get("Id", "").lower()
    ]
    if ctx.obj["json"]:
        output_json(matches)
        return
    click.secho(
        f"\n{len(matches)} matches for {query!r}\n",
        fg="green",
        bold=True,
    )
    print_table(
        matches, ["Name", "Id", "Version", "Type", "Managed"]
    )


@cli.command()
@click.option("--limit", default=0, help="Max apps to check (0=all).")
@click.pass_context
def detective(ctx, limit):
    """Check installed apps for remote-version updates."""
    _progress(ctx, "Running version detective...")
    from src.logic.config import ConfigManager
    from src.logic.parser import get_total_inventory
    from src.logic.remote_versions import check_remote_version

    data = get_total_inventory()
    config = ConfigManager()
    results = []
    checked = 0
    fallback_values = set(config.url_fallbacks.values())
    for item in data:
        url = item.get("URL")
        if not url:
            for key, fallback in config.url_fallbacks.items():
                if key in item["Name"].lower():
                    url = fallback
                    break
        if not url:
            continue
        if not (
            "github.com" in url
            or "release" in url.lower()
            or url in fallback_values
        ):
            continue

        checked += 1
        if limit and checked > limit:
            break
        if not ctx.obj["json"]:
            click.echo(f"  Checking {item['Name']}... ", nl=False)
        remote = check_remote_version(url, item.get("Version"))
        if remote:
            results.append(
                {
                    "Name": item["Name"],
                    "Id": item.get("Id", ""),
                    "Installed": item["Version"],
                    "Available": remote,
                    "URL": url,
                }
            )
            if not ctx.obj["json"]:
                click.secho(
                    f"UPDATE: {item['Version']} -> {remote}", fg="green"
                )
        elif not ctx.obj["json"]:
            click.secho("up to date", fg="bright_black")

    if ctx.obj["json"]:
        output_json(results)
        return
    if results:
        click.secho(
            f"\n{len(results)} updates found (checked {checked} apps)\n",
            fg="green",
            bold=True,
        )
        print_table(results, ["Name", "Installed", "Available"])
    else:
        click.secho(
            f"\nAll {checked} checked apps are up to date.", fg="green"
        )


@cli.command()
@click.pass_context
def status(ctx):
    """Show system summary: counts, versions, health."""
    _progress(ctx, "Gathering system status...")
    from src.logic.parser import get_registry_data, get_total_inventory

    reg_data = get_registry_data()
    data = get_total_inventory(reg_data=reg_data)
    output = _require_success(run_upgrade_scan())
    try:
        updates = parse_winget_upgrade_strict(
            output, reg_data=reg_data
        )
    except WingetParseError as exc:
        raise click.ClickException(
            f"could not parse winget upgrade output safely: {exc}"
        ) from exc

    summary = {
        "total_apps": len(data),
        "installed": sum(
            1 for item in data if item.get("Type") == "Installed"
        ),
        "portable": sum(
            1 for item in data if item.get("Type") == "Portable"
        ),
        "unknown_versions": sum(
            1
            for item in data
            if str(item.get("Version", "")).lower()
            in {"unknown", "???"}
        ),
        "updates_available": len(updates),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if ctx.obj["json"]:
        output_json(summary)
        return

    click.echo()
    click.secho("Winget Universal Dashboard", fg="cyan", bold=True)
    click.echo(f"  Total Applications: {summary['total_apps']}")
    click.echo(f"  Installed: {summary['installed']}")
    click.echo(f"  Portable: {summary['portable']}")
    click.echo(f"  Updates Available: {summary['updates_available']}")
    click.echo(f"  Unknown Versions: {summary['unknown_versions']}")
    click.echo(f"  Time: {summary['timestamp']}")


def main():
    """Run the Click command group."""
    cli(obj={})


if __name__ == "__main__":
    main()
