import logging
import re

logger = logging.getLogger(__name__)

# Strict pattern for winget package IDs (C1 fix)
_VALID_APP_ID_RE = re.compile(r'^[A-Za-z0-9._\-]+$')
_VALID_PACKAGE_NAME_RE = re.compile(r'^[^\r\n\x00]+$')


def validate_app_id(app_id):
    """Validate that an app_id is safe for winget commands.

    Raises ValueError if the ID contains characters that could
    be interpreted as arguments or shell metacharacters.
    """
    if not app_id or not _VALID_APP_ID_RE.match(app_id):
        raise ValueError(
            f"Invalid app ID rejected: {app_id!r}"
        )
    return app_id


def is_valid_app_id(app_id):
    """Return whether a string is a safe winget package ID."""
    return bool(app_id and _VALID_APP_ID_RE.match(str(app_id)))


def validate_package_name(package_name):
    """Validate package names passed as a single QProcess argument."""
    if (
        not package_name
        or not _VALID_PACKAGE_NAME_RE.match(str(package_name))
    ):
        raise ValueError(
            f"Invalid package name rejected: {package_name!r}"
        )
    return str(package_name).strip()


class WingetExecutor:
    """Generates command lists for executing winget operations."""

    def __init__(self):
        self.base_args = [
            "--silent",
            "--accept-package-agreements",
            "--accept-source-agreements"
        ]
        logger.debug("WingetExecutor initialized with base args.")

    def get_check_updates_cmd(self):
        """Command to check for all available updates."""
        cmd = ["winget", "upgrade", "--include-unknown"]
        logger.debug(f"Generated command: {' '.join(cmd)}")
        return cmd

    def get_update_cmd(
        self, package_ref, match_by="id", silent=True
    ):
        """Command to update a specific app by ID or name."""
        if match_by == "id":
            package_ref = validate_app_id(package_ref)
            selector = "--id"
            log_label = "ID"
        elif match_by == "name":
            package_ref = validate_package_name(package_ref)
            selector = "--name"
            log_label = "name"
        else:
            raise ValueError(f"Unsupported winget match field: {match_by!r}")

        cmd = ["winget", "upgrade", selector, package_ref]
        if silent:
            cmd.append("--silent")
        cmd += self.base_args[1:]
        logger.info(
            "Preparing update command for %s: %s (silent=%s)",
            log_label,
            package_ref,
            silent,
        )
        return cmd

    def get_update_all_cmd(self):
        """Command to update all apps."""
        cmd = (
            ["winget", "upgrade", "--all", "--include-unknown"]
            + self.base_args
        )
        logger.info(
            "Preparing bulk update command for all applications."
        )
        return cmd
