"""Runtime access to the source revision embedded in an installed artifact."""

import os
import subprocess
from typing import Any, Dict, Optional, Tuple

from ._build_info import SOURCE_COMMIT, SOURCE_DIRTY


def _source_checkout_info() -> Tuple[str, Optional[bool]]:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.exists(os.path.join(root, ".git")):
        return SOURCE_COMMIT, SOURCE_DIRTY
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            timeout=5,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=root,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            timeout=5,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return SOURCE_COMMIT, SOURCE_DIRTY
    return commit or SOURCE_COMMIT, bool(status.strip())


def source_provenance() -> Dict[str, Any]:
    """Return build provenance without requiring git in installed environments."""
    commit = SOURCE_COMMIT
    dirty = SOURCE_DIRTY
    if commit == "unknown":
        commit, dirty = _source_checkout_info()
    return {"source_commit": commit, "source_dirty": dirty}
