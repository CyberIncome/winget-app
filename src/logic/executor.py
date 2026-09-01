"""Safe construction of Winget command argument lists."""

import logging
import re


logger = logging.getLogger(__name__)

_VALID_APP_ID_RE = re.compile(r"^[A-Za-z0-9._\-]+$")
_VALID_PACKAGE_NAME_RE = re.compile(r"^[^\r\n\x00]+$")
_VALID_SOURCE_NAME_RE = re.compile(r"^[^-\r\n\x00][^\r\n\x00]*$")


def validate_app_id(app_id):
    """Validate a Winget package ID before adding it as an argument."""
    if not app_id or not _VALID_APP_ID_RE.match(str(app_id)):
        raise ValueError(f"Invalid app ID rejected: {app_id!r}")
    return str(app_id)


def is_valid_app_id(app_id):
    """Return whether a string is a safe Winget package ID."""
    return bool(app_id and _VALID_APP_ID_RE.match(str(app_id)))


def validate_package_name(package_name):
    """Validate a package name passed as one process argument."""
    if (
        not package_name
        or not _VALID_PACKAGE_NAME_RE.match(str(package_name))
    ):
        raise ValueError(
            f"Invalid package name rejected: {package_name!r}"
        )
    value = str(package_name).strip()
    if not value or value.startswith("-"):
        raise ValueError(
            f"Invalid package name rejected: {package_name!r}"
        )
    return value


def validate_source_name(source_name):
    """Validate an optional Winget source name used as one CLI argument."""
    if source_name is None or str(source_name).strip() == "":
        return ""
    value = str(source_name).strip()
    if not _VALID_SOURCE_NAME_RE.match(value):
        raise ValueError(f"Invalid source name rejected: {source_name!r}")
    return value


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
    ):
        """Return a command to update one exact package by ID/name and source."""
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
        cmd = [
            "winget",
            "upgrade",
            selector,
            package_ref,
            "--exact",
        ]
        if source:
            cmd.extend(["--source", source])
        if silent:
            cmd.append("--silent")
        cmd.extend(self.noninteractive_args)
        logger.info(
            "Preparing update command for %s: %s source=%s (silent=%s)",
            log_label,
            package_ref,
            source or "default",
            silent,
        )
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
