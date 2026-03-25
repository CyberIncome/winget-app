"""Winget Universal Dashboard — CLI interface.

Exposes the same operations as the GUI for scripting,
automation, and programmatic access.

Usage:
    python -m src.cli check
    python -m src.cli inventory
    python -m src.cli update Google.Chrome
    python -m src.cli update --all
    python -m src.cli search chrome
    python -m src.cli detective
    python -m src.cli status
"""

import json
import logging
import subprocess
import sys
import time

import click

from src.logic.parser import (
    parse_winget_upgrade,
    parse_winget_show_version,
    get_total_inventory,
    get_registry_data,
    check_remote_version,
    is_version_newer,
)
from src.logic.config import ConfigManager
from src.logic.executor import WingetExecutor, validate_app_id


# ── Logging setup ───────────────────────────────────

def setup_logging(verbose):
    """Configure logging for CLI output."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )


# ── Helpers ─────────────────────────────────────────

def run_winget(args, timeout=300):
    """Run a winget command and return stdout."""
    cmd = ["winget"] + args
    logging.debug(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        logging.error(
            f"Command timed out after {timeout}s"
        )
        return ""
    except FileNotFoundError:
        logging.error(
            "winget not found. Is it installed and "
            "on your PATH?"
        )
        sys.exit(1)


def print_table(rows, columns, widths=None):
    """Print a formatted ASCII table."""
    if not rows:
        click.echo("  (no results)")
        return

    if widths is None:
        widths = {}
        for col in columns:
            max_w = len(col)
            for row in rows:
                val = str(row.get(col, ""))
                max_w = max(max_w, len(val))
            widths[col] = min(max_w + 2, 50)

    # Header
    header = ""
    for col in columns:
        header += str(col).ljust(widths[col])
    click.secho(header, fg="cyan", bold=True)
    click.echo("─" * sum(widths.values()))

    # Rows
    for row in rows:
        line = ""
        for col in columns:
            val = str(row.get(col, ""))
            if len(val) > widths[col] - 2:
                val = val[: widths[col] - 5] + "..."
            line += val.ljust(widths[col])

        # Highlight unknowns in yellow
        version = str(row.get("Version", "")).lower()
        if "unknown" in version or "???" in version:
            click.secho(line, fg="yellow")
        elif row.get("Available"):
            click.secho(line, fg="green")
        else:
            click.echo(line)


def output_json(data):
    """Print JSON to stdout."""
    click.echo(json.dumps(data, indent=2, default=str))


# ── CLI Group ───────────────────────────────────────

@click.group()
@click.option(
    "-v", "--verbose", is_flag=True,
    help="Enable debug logging.",
)
@click.option(
    "--json-output", "use_json", is_flag=True,
    help="Output results as JSON.",
)
@click.pass_context
def cli(ctx, verbose, use_json):
    """Winget Universal Dashboard — CLI

    Manage Windows packages from the command line.
    All commands support --json-output for machine-
    readable output.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = use_json
    ctx.obj["verbose"] = verbose
    setup_logging(verbose)


# ── check ───────────────────────────────────────────

@cli.command()
@click.pass_context
def check(ctx):
    """Check for available updates via winget."""
    click.secho(
        "🔍 Checking for updates...", fg="blue",
    )
    reg_data = get_registry_data()
    output = run_winget(["upgrade", "--include-unknown"])
    results = parse_winget_upgrade(
        output, reg_data=reg_data
    )

    if ctx.obj["json"]:
        output_json(results)
        return

    click.secho(
        f"\n📦 {len(results)} updates available\n",
        fg="green", bold=True,
    )
    print_table(
        results,
        ["Name", "Id", "Version", "Available"],
    )

    # Summary
    unknowns = sum(
        1 for r in results
        if r["Version"].lower() == "unknown"
    )
    if unknowns:
        click.secho(
            f"\n⚠  {unknowns} apps have unknown "
            f"installed versions",
            fg="yellow",
        )


# ── inventory ───────────────────────────────────────

@cli.command()
@click.option(
    "--type", "app_type",
    type=click.Choice(
        ["all", "installed", "portable"],
        case_sensitive=False,
    ),
    default="all",
    help="Filter by app type.",
)
@click.pass_context
def inventory(ctx, app_type):
    """Scan full system inventory (registry + shortcuts)."""
    click.secho(
        "📦 Scanning system inventory...", fg="blue",
    )
    start = time.time()
    data = get_total_inventory()
    elapsed = time.time() - start

    if app_type != "all":
        target = (
            "Installed" if app_type == "installed"
            else "Portable"
        )
        data = [
            d for d in data
            if d.get("Type", "") == target
        ]

    if ctx.obj["json"]:
        output_json(data)
        return

    click.secho(
        f"\n📦 {len(data)} applications found "
        f"({elapsed:.1f}s)\n",
        fg="green", bold=True,
    )
    print_table(
        data,
        ["Name", "Version", "Type", "Managed"],
    )

    # Stats
    types = {}
    unknowns = 0
    for d in data:
        t = d.get("Type", "Unknown")
        types[t] = types.get(t, 0) + 1
        v = str(d.get("Version", "")).lower()
        if v in ("unknown", "???"):
            unknowns += 1

    click.echo(f"\n  Types: ", nl=False)
    for t, c in sorted(types.items()):
        click.echo(f"{t}={c}  ", nl=False)
    click.echo()
    if unknowns:
        click.secho(
            f"  ⚠  {unknowns} unknown versions",
            fg="yellow",
        )


# ── update ──────────────────────────────────────────

@cli.command()
@click.argument("app_id", required=False)
@click.option(
    "--all", "update_all", is_flag=True,
    help="Update all available packages.",
)
@click.pass_context
def update(ctx, app_id, update_all):
    """Update a specific app or all apps.

    Examples:
        update Google.Chrome
        update --all
    """
    executor = WingetExecutor()

    if update_all:
        click.secho(
            "⬆  Updating all packages...",
            fg="green", bold=True,
        )
        cmd = executor.get_update_all_cmd()
        _run_update_live(cmd)
        return

    if not app_id:
        click.secho(
            "Error: provide an app ID or use --all",
            fg="red",
        )
        raise SystemExit(1)

    try:
        validate_app_id(app_id)
    except ValueError as e:
        click.secho(f"Error: {e}", fg="red")
        raise SystemExit(1)

    click.secho(
        f"⬆  Updating {app_id}...",
        fg="green", bold=True,
    )
    cmd = executor.get_update_cmd(app_id)
    _run_update_live(cmd)


def _run_update_live(cmd):
    """Run an update command with live output."""
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        for line in process.stdout:
            click.echo(f"  {line}", nl=False)
        process.wait()
        if process.returncode == 0:
            click.secho(
                "\n✅ Update complete.", fg="green",
            )
        else:
            click.secho(
                f"\n⚠  Exited with code "
                f"{process.returncode}",
                fg="yellow",
            )
    except FileNotFoundError:
        click.secho(
            "Error: winget not found.", fg="red",
        )
        raise SystemExit(1)


# ── search ──────────────────────────────────────────

@cli.command()
@click.argument("query")
@click.pass_context
def search(ctx, query):
    """Search installed applications by name or ID."""
    click.secho(
        f"🔍 Searching for '{query}'...", fg="blue",
    )
    data = get_total_inventory()
    query_lower = query.lower()
    matches = [
        d for d in data
        if (
            query_lower in d.get("Name", "").lower()
            or query_lower in d.get("Id", "").lower()
        )
    ]

    if ctx.obj["json"]:
        output_json(matches)
        return

    click.secho(
        f"\n🔎 {len(matches)} matches for '{query}'\n",
        fg="green", bold=True,
    )
    print_table(
        matches,
        ["Name", "Id", "Version", "Type", "Managed"],
    )


# ── detective ───────────────────────────────────────

@cli.command()
@click.option(
    "--limit", default=0,
    help="Max apps to check (0=all).",
)
@click.pass_context
def detective(ctx, limit):
    """Check installed apps for remote version updates.

    Scans HelpLink/URLInfoAbout URLs and GitHub repos
    to find newer versions of locally installed software.
    """
    click.secho(
        "🔍 Running version detective...", fg="blue",
    )
    data = get_total_inventory()
    results = []
    checked = 0

    config = ConfigManager()
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
            or url in config.url_fallbacks.values()
        ):

            continue

        checked += 1
        if limit and checked > limit:
            break

        click.echo(
            f"  Checking {item['Name']}... ", nl=False
        )
        remote_v = check_remote_version(
            url, installed_version=item["Version"]
        )
        if remote_v:
            click.secho(
                f"UPDATE: {item['Version']} → {remote_v}",
                fg="green",
            )
            results.append({
                "Name": item["Name"],
                "Id": item.get("Id", ""),
                "Installed": item["Version"],
                "Available": remote_v,
                "URL": url,
            })
        else:
            click.secho("up to date", fg="bright_black")

    if ctx.obj["json"]:
        output_json(results)
        return

    if results:
        click.secho(
            f"\n🔄 {len(results)} updates found "
            f"(checked {checked} apps)\n",
            fg="green", bold=True,
        )
        print_table(
            results,
            ["Name", "Installed", "Available"],
        )
    else:
        click.secho(
            f"\n✅ All {checked} checked apps are "
            f"up to date.",
            fg="green",
        )


# ── status ──────────────────────────────────────────

@cli.command()
@click.pass_context
def status(ctx):
    """Show system summary: counts, versions, health."""
    click.secho(
        "📊 Gathering system status...", fg="blue",
    )

    # Inventory
    data = get_total_inventory()
    total = len(data)
    installed = sum(
        1 for d in data if d.get("Type") == "Installed"
    )
    portable = sum(
        1 for d in data if d.get("Type") == "Portable"
    )
    unknown_ver = sum(
        1 for d in data
        if str(d.get("Version", "")).lower()
        in ("unknown", "???")
    )

    # Updates
    output = run_winget(["upgrade", "--include-unknown"])
    updates = parse_winget_upgrade(output)

    summary = {
        "total_apps": total,
        "installed": installed,
        "portable": portable,
        "unknown_versions": unknown_ver,
        "updates_available": len(updates),
        "timestamp": time.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    }

    if ctx.obj["json"]:
        output_json(summary)
        return

    click.echo()
    click.secho(
        "  ╔══════════════════════════════════╗",
        fg="cyan",
    )
    click.secho(
        "  ║   Winget Universal Dashboard     ║",
        fg="cyan",
    )
    click.secho(
        "  ╚══════════════════════════════════╝",
        fg="cyan",
    )
    click.echo()
    click.echo(
        f"  📦 Total Applications:  "
        f"{click.style(str(total), bold=True)}"
    )
    click.echo(
        f"     ├─ Installed:        {installed}"
    )
    click.echo(
        f"     └─ Portable:         {portable}"
    )
    click.echo()

    update_color = "green" if not updates else "yellow"
    click.secho(
        f"  🔄 Updates Available:   {len(updates)}",
        fg=update_color, bold=True,
    )

    if unknown_ver:
        click.secho(
            f"  ⚠  Unknown Versions:   {unknown_ver}",
            fg="yellow",
        )
    else:
        click.secho(
            "  ✅ All versions known", fg="green",
        )

    click.echo(
        f"\n  🕐 {summary['timestamp']}"
    )

    if updates:
        click.echo()
        click.secho("  Pending updates:", bold=True)
        for u in updates[:10]:
            click.echo(
                f"    • {u['Name']}  "
                f"{u['Version']} → {u['Available']}"
            )
        if len(updates) > 10:
            click.echo(
                f"    ... and {len(updates) - 10} more"
            )


# ── Entry point ─────────────────────────────────────

def main():
    cli(obj={})


if __name__ == "__main__":
    main()
