import logging

logger = logging.getLogger(__name__)

class WingetExecutor:
    """
    Generates command lists for executing winget operations with logging.
    """
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
        cmd = ["winget", "upgrade", "--id", app_id] + self.base_args
        logger.info(f"Preparing update command for ID: {app_id}")
        return cmd
    
    def get_update_all_cmd(self):
        """Command to update all apps."""
        cmd = ["winget", "upgrade", "--all", "--include-unknown"] + self.base_args
        logger.info("Preparing bulk update command for all applications.")
        return cmd