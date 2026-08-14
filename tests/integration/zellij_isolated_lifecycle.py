#!/usr/bin/env python3
"""Run installed MCP lifecycle probes in an isolated zellij socket namespace."""

import json
import os
import shutil
import subprocess
import sys
import tempfile

from installed_wheel_smoke import run
from zellij_pane_lifecycle import run_probe as run_pane_probe
from zellij_tab_lifecycle import run_probe as run_tab_probe

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    """Build/install once, then exercise pane and Tab lifecycle in isolation."""
    if shutil.which("zellij") is None:
        raise RuntimeError("zellij is required for the isolated lifecycle probe")
    source_commit = run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
    ).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="zmcp-live-") as directory:
        wheel_dir = os.path.join(directory, "wheel")
        build_environment = dict(os.environ)
        build_environment.update({
            "ZELLIJ_MCP_SOURCE_COMMIT": source_commit,
            "ZELLIJ_MCP_SOURCE_DIRTY": "true",
        })
        run(
            [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", wheel_dir],
            cwd=PROJECT_ROOT,
            env=build_environment,
        )
        wheel = next(
            os.path.join(wheel_dir, name)
            for name in os.listdir(wheel_dir)
            if name.endswith(".whl")
        )
        venv_dir = os.path.join(directory, "venv")
        run([sys.executable, "-m", "venv", venv_dir])
        python_path = os.path.join(venv_dir, "bin", "python")
        run([python_path, "-m", "pip", "install", "--no-deps", wheel])

        isolated_home = os.path.join(directory, "home")
        socket_dir = os.path.join(directory, "s")
        cache_dir = os.path.join(directory, "cache")
        config_dir = os.path.join(directory, "config")
        data_dir = os.path.join(directory, "data")
        state_dir = os.path.join(directory, "state")
        for path in (
            isolated_home,
            socket_dir,
            cache_dir,
            config_dir,
            data_dir,
            state_dir,
        ):
            os.makedirs(path)
        environment = dict(os.environ)
        environment.update({
            "HOME": isolated_home,
            "XDG_CACHE_HOME": cache_dir,
            "XDG_CONFIG_HOME": config_dir,
            "XDG_DATA_HOME": data_dir,
            "XDG_STATE_HOME": state_dir,
            "ZELLIJ_CONFIG_DIR": config_dir,
            "ZELLIJ_SOCKET_DIR": socket_dir,
        })
        for name in ("ZELLIJ", "ZELLIJ_SESSION_NAME", "ZELLIJ_PANE_ID"):
            environment.pop(name, None)
        environment.pop("PYTHONPATH", None)
        environment["PYTHONNOUSERSITE"] = "1"
        command = [
            python_path,
            "-c",
            (
                "from zellij_mcp.server.main import ZellijMCPServer; "
                "ZellijMCPServer().serve_stdio()"
            ),
        ]
        pane_result = run_pane_probe(
            command,
            environment=environment,
            working_directory=isolated_home,
        )
        tab_result = run_tab_probe(
            command,
            environment=environment,
            working_directory=isolated_home,
        )
        remaining = subprocess.run(
            ["zellij", "list-sessions", "--no-formatting"],
            cwd=isolated_home,
            env=environment,
            capture_output=True,
            text=True,
        )
        remaining_text = "{}\n{}".format(
            remaining.stdout,
            remaining.stderr,
        ).strip()
        empty_markers = (
            "no active zellij sessions",
            "no active sessions",
            "no sessions found",
        )
        if remaining.returncode != 0 and any(
            marker in remaining_text.lower() for marker in empty_markers
        ):
            remaining_text = ""
        if remaining.returncode == 0 and remaining_text:
            raise RuntimeError(
                "isolated lifecycle left zellij sessions: {}".format(remaining_text)
            )
        if remaining.returncode != 0 and remaining_text:
            raise RuntimeError(
                "unable to verify isolated zellij cleanup: {}".format(remaining_text)
            )
        print(json.dumps({
            "ok": True,
            "source_commit": source_commit,
            "pane": pane_result,
            "tab": tab_result,
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
