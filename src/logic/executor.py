class WingetExecutor:
    """
    Generates command lists for executing winget operations.
    """
    def __init__(self):
        self.base_args = [
            "--silent",
            "--accept-package-agreements",
            "--accept-source-agreements"
        ]

    def get_check_updates_cmd(self):
        """Command to check for all available updates."""
        return ["winget", "upgrade", "--include-unknown"]
    
    def get_update_cmd(self, app_id):
        """Command to update a specific app by ID."""
        return ["winget", "upgrade", "--id", app_id] + self.base_args
    
    def get_update_all_cmd(self):
        """Command to update all apps."""
        return ["winget", "upgrade", "--all", "--include-unknown"] + self.base_args