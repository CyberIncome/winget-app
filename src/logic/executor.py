import logging
import re

logger = logging.getLogger(__name__)

# Strict pattern for winget package IDs (C1 fix)
_VALID_APP_ID_RE = re.compile(r'^[A-Za-z0-9._\-]+$')


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

    def get_update_cmd(self, app_id):
        """Command to update a specific app by ID."""
        app_id = validate_app_id(app_id)
        cmd = ["winget", "upgrade", "--id", app_id] + self.base_args
        logger.info(
            f"Preparing update command for ID: {app_id}"
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