"""Minimal PEP 517 backend for the dependency-free zellij-mcp package."""

import ast
import base64
import hashlib
import os
import re
import subprocess
import zipfile
from typing import Any, Dict, List, Optional, Tuple

PACKAGE_NAME = "zellij_mcp"
DISTRIBUTION = "zellij_mcp"
README_FILENAME = "README.md"
DEVELOPMENT_DEPENDENCIES = (
    "pytest (>=7.0,<8.0)",
    "pytest-cov (>=4.0,<5.0)",
    "coverage (>=7.0,<7.3)",
    "mypy (>=1.0,<1.5)",
    "ruff (>=0.16,<0.17)",
    "bandit (>=1.7.5,<1.8)",
)


def _root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _version() -> str:
    init_path = os.path.join(_root(), PACKAGE_NAME, "__init__.py")
    with open(init_path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=init_path)
    for statement in tree.body:
        if not isinstance(statement, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in statement.targets
        ):
            continue
        try:
            version = ast.literal_eval(statement.value)
        except (ValueError, TypeError, SyntaxError):
            continue
        if isinstance(version, str):
            return version
    raise RuntimeError("zellij-mcp version declaration is missing or invalid")


def _distribution_info(version: str) -> str:
    return "{}-{}.dist-info".format(DISTRIBUTION, version)


def _source_provenance() -> Tuple[str, Optional[bool]]:
    """Resolve the exact checkout revision embedded into build artifacts."""
    configured = os.environ.get("ZELLIJ_MCP_SOURCE_COMMIT", "").strip()
    if configured:
        if re.fullmatch(r"[0-9a-fA-F]{40}", configured) is None:
            raise RuntimeError("ZELLIJ_MCP_SOURCE_COMMIT must be a full commit hash")
        dirty_value = os.environ.get("ZELLIJ_MCP_SOURCE_DIRTY", "").strip().lower()
        dirty = None  # type: Optional[bool]
        if dirty_value in ("1", "true", "yes"):
            dirty = True
        elif dirty_value in ("0", "false", "no"):
            dirty = False
        return configured.lower(), dirty
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=_root(),
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            timeout=5,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=_root(),
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            timeout=5,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "unknown", None
    if re.fullmatch(r"[0-9a-fA-F]{40}", commit) is None:
        return "unknown", None
    return commit.lower(), bool(status.strip())


def _metadata(
    version: str,
    provenance: Optional[Tuple[str, Optional[bool]]] = None,
) -> bytes:
    source_commit, source_dirty = provenance or _source_provenance()
    metadata = (
        "Metadata-Version: 2.4\n"
        "Name: zellij-mcp\n"
        "Version: {}\n"
        "Summary: MCP server for zellij terminal workspace management\n"
        "Author: hymsk\n"
        "Author-email: lxj_hymsk@163.com\n"
        "License-Expression: AGPL-3.0-or-later\n"
        "License-File: LICENSE\n"
        "Requires-Python: >=3.7\n"
        "Description-Content-Type: text/markdown\n"
        "Provides-Extra: dev\n"
        "X-Zellij-MCP-Source-Commit: {}\n"
        "X-Zellij-MCP-Source-Dirty: {}\n"
    ).format(version, source_commit, str(source_dirty).lower())
    for dependency in DEVELOPMENT_DEPENDENCIES:
        metadata += 'Requires-Dist: {} ; extra == "dev"\n'.format(dependency)
    with open(os.path.join(_root(), README_FILENAME), encoding="utf-8") as handle:
        return (metadata + "\n" + handle.read()).encode("utf-8")


def _wheel_metadata() -> bytes:
    return b"Wheel-Version: 1.0\nGenerator: zellij-mcp\nRoot-Is-Purelib: true\nTag: py3-none-any\n"


def _build_info(provenance: Tuple[str, Optional[bool]]) -> bytes:
    source_commit, source_dirty = provenance
    return (
        '"""Source revision embedded by the zellij-mcp build backend."""\n\n'
        'SOURCE_COMMIT = {!r}\nSOURCE_DIRTY = {!r}\n'.format(
            source_commit,
            source_dirty,
        )
    ).encode("utf-8")


def _record_line(path: str, content: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=")
    return "{},sha256={},{}".format(path, digest.decode("ascii"), len(content))


def _package_files() -> List[str]:
    root = _root()
    result = []  # type: List[str]
    package_root = os.path.join(root, PACKAGE_NAME)
    for directory, _unused_dirs, names in os.walk(package_root):
        for name in sorted(names):
            if not name.endswith(".py"):
                continue
            path = os.path.join(directory, name)
            result.append(os.path.relpath(path, root))
    return sorted(result)


def prepare_metadata_for_build_wheel(
    metadata_directory: str,
    config_settings: Optional[Dict[str, Any]] = None,
) -> str:
    """Write the PEP 427 metadata required before building a wheel."""
    version = _version()
    provenance = _source_provenance()
    info_name = _distribution_info(version)
    info_directory = os.path.join(metadata_directory, info_name)
    os.makedirs(info_directory, exist_ok=True)
    with open(os.path.join(info_directory, "METADATA"), "wb") as handle:
        handle.write(_metadata(version, provenance))
    with open(os.path.join(info_directory, "WHEEL"), "wb") as handle:
        handle.write(_wheel_metadata())
    return info_name


def _build_wheel(wheel_directory: str, editable: bool) -> str:
    """Build one regular or editable pure-Python wheel."""
    version = _version()
    provenance = _source_provenance()
    filename = "zellij_mcp-{}-py3-none-any.whl".format(version)
    destination = os.path.join(wheel_directory, filename)
    info_name = _distribution_info(version)
    root = _root()
    files = {}

    if not editable:
        for relative_path in _package_files():
            with open(os.path.join(root, relative_path), "rb") as handle:
                files[relative_path.replace(os.sep, "/")] = handle.read()
        files[PACKAGE_NAME + "/_build_info.py"] = _build_info(provenance)
        with open(os.path.join(root, "LICENSE"), "rb") as handle:
            files[info_name + "/licenses/LICENSE"] = handle.read()
    files[info_name + "/METADATA"] = _metadata(version, provenance)
    files[info_name + "/WHEEL"] = _wheel_metadata()
    files[info_name + "/entry_points.txt"] = (
        b"[console_scripts]\nzellij-mcp = zellij_mcp.cli:main\n"
    )
    if editable:
        files["zellij_mcp.pth"] = (_root() + "\n").encode("utf-8")

    records = [
        _record_line(path, content)
        for path, content in sorted(files.items())
    ]
    record_path = info_name + "/RECORD"
    files[record_path] = ("\n".join(records) + "\n{},,\n".format(record_path)).encode("utf-8")

    os.makedirs(wheel_directory, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in sorted(files.items()):
            archive.writestr(path, content)
    return filename


def build_wheel(
    wheel_directory: str,
    config_settings: Optional[Dict[str, Any]] = None,
    metadata_directory: Optional[str] = None,
) -> str:
    """Build one pure-Python wheel without fetching build dependencies."""
    return _build_wheel(wheel_directory, editable=False)


def prepare_metadata_for_build_editable(
    metadata_directory: str,
    config_settings: Optional[Dict[str, Any]] = None,
) -> str:
    """Expose the same metadata for editable and regular wheels."""
    return prepare_metadata_for_build_wheel(metadata_directory, config_settings)


def build_editable(
    wheel_directory: str,
    config_settings: Optional[Dict[str, Any]] = None,
    metadata_directory: Optional[str] = None,
) -> str:
    """Build a PEP 660 wheel that adds this source tree through a .pth file."""
    return _build_wheel(wheel_directory, editable=True)


def build_sdist(
    sdist_directory: str,
    config_settings: Optional[Dict[str, Any]] = None,
) -> str:
    """This adapter only installs wheels and deliberately does not ship an sdist."""
    raise RuntimeError("zellij-mcp source distributions are not supported")
