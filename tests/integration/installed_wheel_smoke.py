#!/usr/bin/env python3
"""Build, install and smoke the wheel without importing the source checkout."""

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from email.parser import Parser

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run(argv, **kwargs):
    completed = subprocess.run(argv, capture_output=True, text=True, **kwargs)
    if completed.returncode != 0:
        raise RuntimeError(
            "command failed: {}\nstdout:\n{}\nstderr:\n{}".format(
                argv,
                completed.stdout,
                completed.stderr,
            )
        )
    return completed


def main():
    """Assert wheel description, installed tools/list, and source provenance."""
    source_commit = run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
    ).stdout.strip()
    source_dirty = bool(run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=PROJECT_ROOT,
    ).stdout.strip())
    with tempfile.TemporaryDirectory(prefix="zellij-mcp-wheel-") as directory:
        wheel_dir = os.path.join(directory, "wheel")
        environment = dict(os.environ)
        environment.update({
            "ZELLIJ_MCP_SOURCE_COMMIT": source_commit,
            "ZELLIJ_MCP_SOURCE_DIRTY": "true" if source_dirty else "false",
        })
        run(
            [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", wheel_dir],
            cwd=PROJECT_ROOT,
            env=environment,
        )
        if run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT).stdout.strip() != source_commit:
            raise RuntimeError("source HEAD changed while building the wheel")
        wheels = [
            os.path.join(wheel_dir, name)
            for name in os.listdir(wheel_dir)
            if name.endswith(".whl")
        ]
        if len(wheels) != 1:
            raise RuntimeError("expected exactly one wheel, got {}".format(wheels))
        with zipfile.ZipFile(wheels[0]) as archive:
            metadata_paths = [
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_paths) != 1:
                raise RuntimeError("expected exactly one wheel metadata file")
            metadata = Parser().parsestr(archive.read(metadata_paths[0]).decode("utf-8"))
        with open(os.path.join(PROJECT_ROOT, "README.md"), encoding="utf-8") as handle:
            readme = handle.read()
        if metadata.get("Description-Content-Type") != "text/markdown":
            raise RuntimeError("wheel metadata has no Markdown description content type")
        if metadata.get_payload() != readme:
            raise RuntimeError("wheel description does not match the English README")
        venv_dir = os.path.join(directory, "venv")
        run([sys.executable, "-m", "venv", venv_dir])
        executable_dir = "Scripts" if os.name == "nt" else "bin"
        python_path = os.path.join(venv_dir, executable_dir, "python")
        wrapper_path = os.path.join(venv_dir, executable_dir, "zellij-mcp")
        run([python_path, "-m", "pip", "install", "--no-deps", wheels[0]])

        isolated = os.path.join(directory, "isolated")
        os.makedirs(isolated)
        runtime_environment = dict(os.environ)
        runtime_environment.pop("PYTHONPATH", None)
        runtime_environment["PYTHONNOUSERSITE"] = "1"
        version = run(
            [wrapper_path, "version", "--json"],
            cwd=isolated,
            env=runtime_environment,
        )
        version_payload = json.loads(version.stdout)
        if version_payload.get("source_commit") != source_commit:
            raise RuntimeError("installed source_commit does not match the checkout")
        if version_payload.get("source_dirty") is not source_dirty:
            raise RuntimeError("installed source_dirty does not match the checkout")

        smoke = run(
            [
                python_path,
                os.path.join(PROJECT_ROOT, "tests", "integration", "server_smoke.py"),
                wrapper_path,
                "serve",
            ],
            cwd=isolated,
            env=runtime_environment,
        )
        result = json.loads(smoke.stdout)
        result.update({
            "installed": True,
            "source_commit": source_commit,
            "source_dirty": source_dirty,
            "wheel": os.path.basename(wheels[0]),
            "readme_in_metadata": True,
        })
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
