from __future__ import annotations

import subprocess
from pathlib import Path


class StartupService:
    @staticmethod
    def register_task(task_name: str, python_executable: str, script_path: Path) -> None:
        command = [
            "schtasks",
            "/Create",
            "/F",
            "/SC",
            "ONLOGON",
            "/TN",
            task_name,
            "/TR",
            f'"{python_executable}" "{script_path}"',
        ]
        subprocess.run(command, check=False)
