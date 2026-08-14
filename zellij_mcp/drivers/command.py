"""Single subprocess boundary for zellij command execution."""

import shutil
import subprocess
from typing import List, Optional


class ZellijCommandRunner:
    """Find and execute zellij with bounded argv-only subprocess calls."""

    def __init__(self) -> None:
        self.zellij_path = shutil.which("zellij")

    def command(self, *args: str) -> List[str]:
        return [self.zellij_path or "zellij", *args]

    def run(
        self,
        argv: List[str],
        timeout: float = 5,
        cwd: Optional[str] = None,
        input_text: Optional[str] = None,
    ) -> Optional["subprocess.CompletedProcess[str]"]:
        """Run one zellij argv call and preserve timeout/failure as unknown."""
        try:
            return subprocess.run(
                argv,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=timeout,
                cwd=cwd,
                input=input_text,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
