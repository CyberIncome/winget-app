"""Safe construction of Winget command argument lists."""

from pathlib import Path
import logging
import re


logger = logging.getLogger(__name__)

_VALID_APP_ID_RE = re.compile(r"[A-Za-z0-9._\-]+")
_MAX_VERSION_LENGTH = 256


def _has_control_character(value):
    """Return whether a process argument contains an ASCII control byte."""
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _is_safe_app_id(value):
    """Return whether value can represent a complete exact package ID."""
    return bool(
        value
        and not value.startswith("-")
        and not value.endswith(".")
        and not _has_control_character(value)
        and _VALID_APP_ID_RE.fullmatch(value)
    )


def validate_app_id(app_id):
    """Validate a complete Winget package ID before adding it as an argument."""
    raw = "" if app_id is None else str(app_id)
    if not _is_safe_app_id(raw):
        raise ValueError(f"Invalid app ID rejected: {app_id!r}")
    return raw


def is_valid_app_id(app_id):
    """Return whether a string is a complete safe Winget package ID."""
    if app_id is None:
        return False
    return _is_safe_app_id(str(app_id))


def validate_package_name(package_name):
    """Validate a package name passed as one process argument."""
    raw = "" if package_name is None else str(package_name)
    if not raw or _has_control_character(raw):
        raise ValueError(
            f"Invalid package name rejected: {package_name!r}"
        )
    value = raw.strip()
    if not value or value.startswith("-"):
        raise ValueError(
            f"Invalid package name rejected: {package_name!r}"
        )
    return value


def validate_source_name(source_name):
    """Validate an optional Winget source name used as one CLI argument."""
    if source_name is None:
        return ""
    raw = str(source_name)
    if _has_control_character(raw):
        raise ValueError(f"Invalid source name rejected: {source_name!r}")
    value = raw.strip()
    if not value:
        return ""
    if value.startswith("-"):
        raise ValueError(f"Invalid source name rejected: {source_name!r}")
    return value


def validate_package_version(version):
    """Validate an optional exact source package version as one process argument."""
    if version is None:
        return ""
    raw = str(version)
    if _has_control_character(raw):
        raise ValueError(f"Invalid package version rejected: {version!r}")
    value = raw.strip()
    if not value:
        return ""
    if value.startswith("-") or len(value) > _MAX_VERSION_LENGTH:
        raise ValueError(f"Invalid package version rejected: {version!r}")
    return value


def validate_output_path(output_path):
    """Validate one explicit absolute output-file path for Winget export."""
    raw = "" if output_path is None else str(output_path)
    if not raw or _has_control_character(raw):
        raise ValueError(f"Invalid output path rejected: {output_path!r}")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ValueError("Winget export output path must be absolute")
    return str(path)


class WingetExecutor:
    """Generate non-shell Winget command argument lists."""

    def __init__(self):
        self.noninteractive_args = [
            "--accept-package-agreements",
            "--accept-source-agreements",
            "--disable-interactivity",
        ]
        logger.debug("WingetExecutor initialized.")

    def get_check_updates_cmd(self):
        """Return a non-interactive command to enumerate available updates."""
        cmd = [
            "winget",
            "upgrade",
            "--include-unknown",
            "--accept-source-agreements",
            "--disable-interactivity",
        ]
        logger.debug("Generated command: %s", " ".join(cmd))
        return cmd

    def get_update_cmd(
        self,
        package_ref,
        match_by="id",
        silent=True,
        source=None,
        version=None,
    ):
        """Return an exact package/source/version upgrade command."""
        if match_by == "id":
            package_ref = validate_app_id(package_ref)
            selector = "--id"
            log_label = "ID"
        elif match_by == "name":
            package_ref = validate_package_name(package_ref)
            selector = "--name"
            log_label = "name"
        else:
            raise ValueError(
                f"Unsupported winget match field: {match_by!r}"
            )

        source = validate_source_name(source)
        version = validate_package_version(version)
        cmd = [
            "winget",
            "upgrade",
            selector,
            package_ref,
            "--exact",
        ]
        if source:
            cmd.extend(["--source", source])
        if version:
            cmd.extend(["--version", version])
        if silent:
            cmd.append("--silent")
        cmd.extend(self.noninteractive_args)
        logger.info(
            "Preparing update command for %s: %s source=%s version=%s (silent=%s)",
            log_label,
            package_ref,
            source or "default",
            version or "latest",
            silent,
        )
        return cmd

    def get_show_cmd(self, package_ref, match_by="id", source=None, version=None):
        """Return a non-interactive read-only command for package metadata."""
        if match_by == "id":
            package_ref = validate_app_id(package_ref)
            selector = "--id"
        elif match_by == "name":
            package_ref = validate_package_name(package_ref)
            selector = "--name"
        else:
            raise ValueError(
                f"Unsupported winget match field: {match_by!r}"
            )
        source = validate_source_name(source)
        version = validate_package_version(version)
        cmd = ["winget", "show", selector, package_ref, "--exact"]
        if source:
            cmd.extend(["--source", source])
        if version:
            cmd.extend(["--version", version])
        cmd.extend(["--accept-source-agreements", "--disable-interactivity"])
        return cmd

    def get_export_cmd(self, output_path, *, include_versions=False, source=None):
        """Return a read-only package-list export command."""
        destination = validate_output_path(output_path)
        source = validate_source_name(source)
        cmd = ["winget", "export", "--output", destination]
        if include_versions:
            cmd.append("--include-versions")
        if source:
            cmd.extend(["--source", source])
        cmd.extend(["--accept-source-agreements", "--disable-interactivity"])
        return cmd

    def get_update_all_cmd(self):
        """Return a non-interactive command to update all detected packages."""
        cmd = [
            "winget",
            "upgrade",
            "--all",
            "--include-unknown",
            "--silent",
            *self.noninteractive_args,
        ]
        logger.info(
            "Preparing bulk update command for all applications."
        )
        return cmd
