"""Recover zellij context filtered by a local MCP Host."""

import os
from typing import Any, Callable, Dict, MutableMapping, Optional, Tuple, cast

ZELLIJ_CONTEXT_KEYS = (
    "ZELLIJ",
    "ZELLIJ_SESSION_NAME",
    "ZELLIJ_PANE_ID",
    "XDG_RUNTIME_DIR",
)
MAX_ANCESTOR_DEPTH = 32
MAX_ENVIRONMENT_BYTES = 1024 * 1024
MAX_STATUS_BYTES = 256 * 1024
MAX_STAT_BYTES = 64 * 1024

ProcessReader = Callable[[int], Optional[Dict[str, Any]]]


def _read_bounded(path: str, limit: int) -> bytes:
    with open(path, "rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("process metadata exceeds the recovery limit")
    return data


def _parse_process_stat(data: bytes) -> Tuple[int, int]:
    text = data.decode("ascii", errors="strict").strip()
    closing = text.rfind(")")
    if closing <= 0:
        raise ValueError("invalid process stat")
    fields = text[closing + 1:].strip().split()
    if len(fields) <= 19:
        raise ValueError("incomplete process stat")
    ppid = int(fields[1])
    start_ticks = int(fields[19])
    if ppid < 0 or start_ticks <= 0:
        raise ValueError("invalid process identity")
    return ppid, start_ticks


def _parse_process_uid(data: bytes) -> int:
    text = data.decode("ascii", errors="strict")
    for line in text.splitlines():
        if not line.startswith("Uid:"):
            continue
        fields = line.split()
        if len(fields) < 3:
            break
        real_uid = int(fields[1])
        effective_uid = int(fields[2])
        if real_uid != effective_uid:
            raise ValueError("process real and effective uid differ")
        return real_uid
    raise ValueError("process uid is unavailable")


def _parse_zellij_environment(data: bytes) -> Dict[str, str]:
    result = {}  # type: Dict[str, str]
    prefixes = {
        key.encode("ascii") + b"=": key
        for key in ZELLIJ_CONTEXT_KEYS
    }
    for entry in data.split(b"\0"):
        for prefix, key in prefixes.items():
            if not entry.startswith(prefix):
                continue
            value = entry[len(prefix):].decode("utf-8", errors="strict")
            result[key] = value
            break
    return result


def _read_linux_process(pid: int) -> Optional[Dict[str, Any]]:
    if pid <= 0 or os.name != "posix" or not os.path.isdir("/proc"):
        return None
    process_root = "/proc/{}".format(pid)
    stat_before = _parse_process_stat(
        _read_bounded(os.path.join(process_root, "stat"), MAX_STAT_BYTES)
    )
    uid = _parse_process_uid(
        _read_bounded(os.path.join(process_root, "status"), MAX_STATUS_BYTES)
    )
    environment = _parse_zellij_environment(
        _read_bounded(os.path.join(process_root, "environ"), MAX_ENVIRONMENT_BYTES)
    )
    stat_after = _parse_process_stat(
        _read_bounded(os.path.join(process_root, "stat"), MAX_STAT_BYTES)
    )
    if stat_before != stat_after:
        raise ValueError("process identity changed during environment read")
    return {
        "ppid": stat_before[0],
        "uid": uid,
        "environment": environment,
    }


def _contains_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _valid_context_value(key: str, value: Any) -> bool:
    if not isinstance(value, str) or not value or _contains_control(value):
        return False
    if key in ("ZELLIJ", "ZELLIJ_PANE_ID"):
        return len(value) <= 20 and value.isdigit()
    if key == "ZELLIJ_SESSION_NAME":
        return len(value.encode("utf-8")) <= 256
    if key == "XDG_RUNTIME_DIR":
        return (
            len(value.encode("utf-8")) <= 4096
            and os.path.isabs(value)
            and os.path.normpath(value) == value
        )
    return False


def restore_zellij_context(
    environment: Optional[MutableMapping[str, str]] = None,
    parent_pid: Optional[int] = None,
    current_uid: Optional[int] = None,
    process_reader: Optional[ProcessReader] = None,
) -> Dict[str, str]:
    """Fill missing zellij variables from the nearest same-uid ancestors."""
    target = os.environ if environment is None else environment
    if not hasattr(os, "getuid"):
        return {}
    uid = os.getuid() if current_uid is None else current_uid
    pid = os.getppid() if parent_pid is None else parent_pid
    reader = _read_linux_process if process_reader is None else process_reader
    missing = {
        key
        for key in ZELLIJ_CONTEXT_KEYS
        if key not in target
    }
    imported = {}  # type: Dict[str, str]
    visited = set()

    for _unused_depth in range(MAX_ANCESTOR_DEPTH):
        if not missing or not isinstance(pid, int) or type(pid) is bool or pid <= 1:
            break
        if pid in visited:
            break
        visited.add(pid)
        try:
            process = reader(pid)
        except Exception:
            break
        if not isinstance(process, dict):
            break
        process_uid = process.get("uid")
        if not isinstance(process_uid, int) or type(process_uid) is bool:
            break
        if process_uid != uid:
            break
        process_environment = process.get("environment")
        if not isinstance(process_environment, dict):
            break
        for key in tuple(missing):
            value = process_environment.get(key)
            if not _valid_context_value(key, value):
                continue
            context_value = cast(str, value)
            target[key] = context_value
            imported[key] = context_value
            missing.remove(key)
        next_pid = process.get("ppid")
        if not isinstance(next_pid, int) or type(next_pid) is bool or next_pid <= 0:
            break
        pid = next_pid
    return imported
