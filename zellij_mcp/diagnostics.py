"""Structured runtime diagnostics shared by CLI and MCP."""

import platform
import sys
from typing import Any, Dict

from . import __version__
from .drivers.zellij import ZellijDriver
from .provenance import source_provenance


def build_diagnostics() -> Dict[str, Any]:
    """Build a machine-readable doctor report without installing dependencies."""
    python_compatible = sys.version_info >= (3, 7)
    zellij = ZellijDriver().doctor()
    warnings = list(zellij.get("warnings", []))
    fixes = list(zellij.get("fixes", []))
    zellij_ok = bool(
        zellij.get("available")
        and zellij.get("supports_background_create")
        and zellij.get("supports_stable_tab_control")
        and zellij.get("supports_direct_pane_io", True)
    )
    provenance = source_provenance()
    return {
        "ok": bool(
            python_compatible
            and zellij_ok
        ),
        "zellij-mcp": {
            "version": __version__,
            "server_command": [sys.executable, "-m", "zellij_mcp", "serve"],
            "source_commit": provenance["source_commit"],
            "source_dirty": provenance["source_dirty"],
        },
        "python": {
            "compatible": python_compatible,
            "executable": sys.executable,
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "minimum": "3.7",
        },
        "zellij": zellij,
        "capabilities": {
            "direct_pane_io": bool(zellij.get("supports_direct_pane_io", True)),
        },
        "warnings": warnings,
        "fixes": fixes,
    }
