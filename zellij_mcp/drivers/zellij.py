"""Zellij driver for Zellij MCP Server."""

import json
import os
import re
import tempfile
import time
import uuid
from contextlib import suppress
from typing import Any, Dict, List, Optional, Set, Union

from ..core.types import WorkspaceRef
from .command import ZellijCommandRunner
from .discovery import ZellijDiscovery


class ZellijMutationOutcomeUnknownError(RuntimeError):
    """Signal that zellij may have applied a mutation without a usable result."""


class ZellijDriver:
    """Pure zellij workspace driver.

    Use zellij-native background sessions, explicitly target panes, and avoid
    tmux/screen holders or focused-pane fallbacks for normal operations.
    """

    KEY_NAMES = {
        "Ctrl-C": "Ctrl c",
        "Ctrl-D": "Ctrl d",
        "Escape": "Esc",
    }

    def __init__(self) -> None:
        self._command_runner = ZellijCommandRunner()
        self._discovery = ZellijDiscovery()

    @property
    def zellij_path(self) -> Optional[str]:
        return self._command_runner.zellij_path

    @zellij_path.setter
    def zellij_path(self, value: Optional[str]) -> None:
        self._command_runner.zellij_path = value

    def _cmd(self, *args: str) -> List[str]:
        """Build a zellij command."""
        return self._command_runner.command(*args)

    def _run(
        self,
        argv: List[str],
        *,
        timeout: float = 5,
        cwd: Optional[str] = None,
        input_text: Optional[str] = None,
    ) -> Any:
        """Run a zellij command and capture output."""
        return self._command_runner.run(
            argv,
            timeout=timeout,
            cwd=cwd,
            input_text=input_text,
        )

    def _valid_command(self, command: Optional[List[str]]) -> bool:
        """Return whether an optional argv value is safe to pass to zellij."""
        if command is None:
            return True
        return bool(command) and all(isinstance(item, str) and item for item in command)

    def _cwd_or_default(self, cwd: Optional[str]) -> str:
        return os.path.abspath(cwd or os.getcwd())

    def is_available(self) -> bool:
        """Check if zellij executable is available."""
        return self.zellij_path is not None

    def supports_background_create(self) -> bool:
        """Return whether this zellij supports native detached creation."""
        if not self.is_available():
            return False
        result = self._run(self._cmd("attach", "--help"), timeout=5)
        if result is None or result.returncode != 0:
            return False
        output = f"{result.stdout}\n{result.stderr}"
        return "--create-background" in output

    def supports_stable_tab_control(self) -> bool:
        """Return whether stable Tab actions and direct pane targeting exist."""
        if not self.is_available():
            return False
        action_help = self._run(self._cmd("action", "--help"), timeout=5)
        pane_help = self._run(
            self._cmd("action", "new-pane", "--help"),
            timeout=5,
        )
        if (
            action_help is None
            or action_help.returncode != 0
            or pane_help is None
            or pane_help.returncode != 0
        ):
            return False
        action_text = "{}\n{}".format(action_help.stdout, action_help.stderr)
        pane_text = "{}\n{}".format(pane_help.stdout, pane_help.stderr)
        required_actions = (
            "list-tabs",
            "new-tab",
            "go-to-tab-by-id",
            "rename-tab-by-id",
            "close-tab-by-id",
        )
        return all(action in action_text for action in required_actions) and (
            "--tab-id" in pane_text
        )

    def supports_direct_pane_io(self) -> bool:
        """Return whether zellij can directly write and dump a selected pane."""
        if not self.is_available():
            return False
        for action, required in (
            ("write-chars", ("--pane-id",)),
            ("send-keys", ("--pane-id",)),
            ("dump-screen", ("--pane-id", "--ansi", "--path")),
        ):
            result = self._run(
                self._cmd("action", action, "--help"),
                timeout=5,
            )
            if result is None or result.returncode != 0:
                return False
            output = "{}\n{}".format(result.stdout, result.stderr)
            if not all(option in output for option in required):
                return False
        return True

    def is_inside_zellij(self) -> bool:
        """Check if currently inside zellij."""
        return bool(os.environ.get("ZELLIJ") or os.environ.get("ZELLIJ_PANE_ID"))

    def get_current_pane_id(self) -> Optional[str]:
        """Get current pane ID."""
        pane_id = os.environ.get("ZELLIJ_PANE_ID", "")
        return self.normalize_pane_id(pane_id) if pane_id else None

    def get_current_session(self) -> Optional[str]:
        """Get current zellij session name from zellij context."""
        return os.environ.get("ZELLIJ_SESSION_NAME") or None

    def is_running(self) -> bool:
        """Check if there is at least one active zellij session."""
        return bool(self.list_sessions())

    def list_sessions(self) -> List[str]:
        """List active zellij sessions with parser-friendly output."""
        sessions = self.list_sessions_checked()
        return sessions if sessions is not None else []

    def list_sessions_checked(self) -> Optional[List[str]]:
        """List sessions without collapsing discovery failure into an empty list."""
        return self._list_sessions_checked()

    def _list_sessions_checked(self) -> Optional[List[str]]:
        """List sessions while preserving discovery failure versus confirmed empty."""
        if not self.is_available():
            return None
        result = self._run(
            self._cmd("list-sessions", "--no-formatting"),
            timeout=5,
        )
        if result is None:
            return None
        if result.returncode == 0:
            return self._parse_active_sessions(result.stdout)
        output = "{}\n{}".format(result.stdout, result.stderr).lower()
        empty_markers = (
            "no active zellij sessions",
            "no active sessions",
            "no sessions found",
        )
        if any(marker in output for marker in empty_markers):
            return []
        return None

    def _parse_active_sessions(self, text: str) -> List[str]:
        """Exclude zellij's exited, resurrectable session records."""
        return self._discovery.parse_active_sessions(text)

    def session_presence(self, session: str) -> Optional[bool]:
        """Return True, False, or None when session discovery is unavailable."""
        sessions = self._list_sessions_checked()
        if sessions is None:
            return None
        return session in sessions

    def create_session_with_command(
        self,
        name: str,
        cwd: Optional[str] = None,
        command: Optional[List[str]] = None,
    ) -> Optional[WorkspaceRef]:
        """Create a background session and start command as its initial pane."""
        if not self.supports_background_create():
            return None
        if not self._valid_command(command):
            return None

        presence = self.session_presence(name)
        if presence is None:
            return None
        if presence:
            return None

        if command:
            pane_id = self._attach_background_session_with_layout(name, cwd, command)
            if pane_id is None:
                return None
        else:
            if not self._attach_background_session(name, cwd=cwd):
                return None
            pane_id = self._wait_for_terminal_pane(name)
            if pane_id is None:
                if self.close_session(name):
                    return None
                raise ZellijMutationOutcomeUnknownError(
                    "created session terminal pane could not be discovered"
                )
        self.close_startup_plugin_panes(name)
        return WorkspaceRef(resource_type="session", session=name, pane=pane_id)

    def _wait_for_terminal_pane(self, session: str) -> Optional[str]:
        """Wait briefly for a new background session's terminal pane identity."""
        for _unused_attempt in range(40):
            panes = self.list_panes_checked(session, include_plugins=True)
            if panes is not None:
                terminal_panes = [pane for pane in panes if not pane.get("is_plugin")]
                focused = [pane for pane in terminal_panes if pane.get("is_focused")]
                candidates = focused if len(focused) == 1 else terminal_panes
                if len(candidates) == 1:
                    pane_id = candidates[0].get("pane_id")
                    if isinstance(pane_id, str) and pane_id:
                        return pane_id
            time.sleep(0.05)
        return None

    def _attach_background_session(self, name: str, cwd: Optional[str] = None) -> bool:
        """Create or attach a zellij background session using zellij itself."""
        command = self._cmd(
            "attach",
            "-b",
            name,
            "options",
            "--default-cwd",
            self._cwd_or_default(cwd),
            "--show-startup-tips",
            "false",
            "--show-release-notes",
            "false",
        )
        result = self._run(command, timeout=10, cwd=self._cwd_or_default(cwd))
        if result is None:
            if self.session_presence(name) is True:
                return True
            raise ZellijMutationOutcomeUnknownError(
                "background session creation timed out"
            )
        if result.returncode == 0:
            return True
        output = f"{result.stdout}\n{result.stderr}"
        return "Session already exists" in output

    def _attach_background_session_with_layout(
        self,
        name: str,
        cwd: Optional[str],
        command: List[str],
    ) -> Optional[str]:
        """Create a background session and return its discovered terminal pane."""
        layout_path = ""
        result = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                prefix="zellij-mcp-zellij-",
                suffix=".kdl",
                delete=False,
            ) as handle:
                layout_path = handle.name
                handle.write(self.layout_for_command(command, cwd))

            zellij_command = self._cmd(
                "attach",
                "-b",
                name,
                "options",
                "--default-layout",
                layout_path,
                "--default-cwd",
                self._cwd_or_default(cwd),
                "--show-startup-tips",
                "false",
                "--show-release-notes",
                "false",
            )
            result = self._run(zellij_command, timeout=10, cwd=self._cwd_or_default(cwd))
            if result is None:
                if self.session_presence(name) is not True:
                    raise ZellijMutationOutcomeUnknownError(
                        "background session creation timed out"
                    )
            elif result.returncode != 0:
                return None

            pane_id = self._wait_for_terminal_pane(name)
            if pane_id is not None:
                return pane_id
            if self.close_session(name):
                return None
            raise ZellijMutationOutcomeUnknownError(
                "created session terminal pane could not be discovered"
            )
        finally:
            if layout_path:
                with suppress(FileNotFoundError):
                    os.unlink(layout_path)

    def layout_for_command(self, command: List[str], cwd: Optional[str]) -> str:
        """Build a minimal zellij layout for an initial command pane."""
        if not self._valid_command(command):
            raise ValueError("command must be a non-empty argv list")
        command_node = json.dumps(command[0], ensure_ascii=False)
        cwd_node = json.dumps(self._cwd_or_default(cwd), ensure_ascii=False)
        lines = [
            "layout {",
            f"    pane command={command_node} cwd={cwd_node} {{",
        ]
        if len(command) > 1:
            args = " ".join(json.dumps(arg, ensure_ascii=False) for arg in command[1:])
            lines.append(f"        args {args}")
        lines.extend(["    }", "}", ""])
        return "\n".join(lines)

    def action_command(self, session: Optional[str], action: str) -> List[str]:
        """Build a zellij action command, optionally targeting a session."""
        command = self._cmd()
        if session:
            command.extend(["--session", session])
        command.extend(["action", action])
        return command

    def list_tabs_checked(
        self,
        session: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """List tabs without collapsing command or parse failures into absence."""
        if not self.is_available():
            return None
        if not session and not self.is_inside_zellij():
            return None

        result = self._run(
            self.action_command(session, "list-tabs") + ["--json", "--all"],
            timeout=5,
        )
        if result is None or result.returncode != 0:
            return None
        try:
            payload = json.loads(result.stdout)
        except (TypeError, ValueError):
            return None
        tabs = self._normalize_tabs(payload)
        return tabs if tabs or payload == [] else None

    def create_tab(
        self,
        session: Optional[str] = None,
        name: Optional[str] = None,
        cwd: Optional[str] = None,
        command: Optional[List[str]] = None,
    ) -> Optional[int]:
        """Create a tab and return its stable ID without using a shell string."""
        if not self.is_available() or not self._valid_command(command):
            return None
        if not session and not self.is_inside_zellij():
            return None

        resolved_cwd = self._cwd_or_default(cwd)
        tabs_before = self.list_tabs_checked(session)
        if tabs_before is None:
            return None
        tab_ids_before = {
            tab.get("tab_id")
            for tab in tabs_before
            if isinstance(tab.get("tab_id"), int)
        }

        cmd = self.action_command(session, "new-tab")
        if cwd:
            cmd.extend(["--cwd", resolved_cwd])
        if name:
            cmd.extend(["--name", name])
        if command:
            cmd.append("--no-focus")
            cmd.append("--")
            cmd.extend(command)

        result = self._run(cmd, timeout=10, cwd=resolved_cwd)
        if result is None:
            tabs_after = self.list_tabs_checked(session)
            if tabs_after is None:
                raise ZellijMutationOutcomeUnknownError("Tab creation timed out")
            created = [
                tab.get("tab_id")
                for tab in tabs_after
                if isinstance(tab.get("tab_id"), int)
                and tab.get("tab_id") not in tab_ids_before
            ]
            if len(created) == 1:
                return created[0]
            raise ZellijMutationOutcomeUnknownError("Tab creation timed out")
        if result.returncode != 0:
            return None

        output = result.stdout.strip()
        if output.isdigit():
            return int(output)

        tabs_after = self.list_tabs_checked(session)
        if tabs_after is None:
            raise ZellijMutationOutcomeUnknownError(
                "created Tab could not be discovered"
            )
        created = [
            tab.get("tab_id")
            for tab in tabs_after
            if isinstance(tab.get("tab_id"), int)
            and tab.get("tab_id") not in tab_ids_before
        ]
        if len(created) == 1:
            return created[0]
        raise ZellijMutationOutcomeUnknownError("created Tab identity is ambiguous")

    def focus_tab(self, session: str, tab_id: int) -> bool:
        """Make one stable tab ID active in the selected session."""
        if not self.is_available():
            return False
        result = self._run(
            self.action_command(session, "go-to-tab-by-id") + [str(tab_id)],
            timeout=5,
        )
        if result is not None and result.returncode == 0:
            return True
        tabs = self.list_tabs_checked(session)
        return bool(
            tabs is not None
            and any(
                tab.get("tab_id") == tab_id and tab.get("active") is True
                for tab in tabs
            )
        )

    def rename_tab(self, session: str, tab_id: int, name: str) -> bool:
        """Rename one tab by stable ID."""
        if not self.is_available() or not name:
            return False
        result = self._run(
            self.action_command(session, "rename-tab-by-id")
            + [str(tab_id), name],
            timeout=5,
        )
        if result is not None and result.returncode == 0:
            return True
        tabs = self.list_tabs_checked(session)
        return bool(
            tabs is not None
            and any(
                tab.get("tab_id") == tab_id and tab.get("name") == name
                for tab in tabs
            )
        )

    def close_tab(self, session: str, tab_id: int) -> bool:
        """Close one tab by stable ID and verify an ambiguous failure."""
        if not self.is_available():
            return False
        result = self._run(
            self.action_command(session, "close-tab-by-id") + [str(tab_id)],
            timeout=5,
        )
        if result is not None and result.returncode == 0:
            return True
        tabs = self.list_tabs_checked(session)
        return tabs is not None and all(
            tab.get("tab_id") != tab_id for tab in tabs
        )

    def _normalize_tabs(self, payload: Any) -> List[Dict[str, Any]]:
        """Normalize zellij tab JSON across compatible output variants."""
        return self._discovery.normalize_tabs(payload)

    def _non_negative_int(self, value: Any) -> Optional[int]:
        """Normalize an integer-like zellij field without accepting booleans."""
        return self._discovery.non_negative_int(value)

    def create_pane(
        self,
        session: Optional[str] = None,
        name: Optional[str] = None,
        cwd: Optional[str] = None,
        command: Optional[List[str]] = None,
        tab_id: Optional[int] = None,
    ) -> Optional[WorkspaceRef]:
        """Create a new pane in the current or an explicitly named session."""
        if not self.is_available():
            return None
        if not self._valid_command(command):
            return None
        if tab_id is not None and (
            type(tab_id) is not int or tab_id < 0
        ):
            return None

        action_session = session
        report_session = session
        if not action_session:
            if not self.is_inside_zellij():
                return None
            report_session = self.get_current_session() or "current"

        resolved_cwd = self._cwd_or_default(cwd)
        pane_name = name or "zellij-mcp-{}".format(uuid.uuid4().hex[:12])
        panes_before = self.list_panes_checked(action_session, include_plugins=True)
        if panes_before is None:
            return None
        pane_ids_before = set()  # type: Set[str]
        for pane in panes_before:
            existing_pane_id = pane.get("pane_id")
            if isinstance(existing_pane_id, str):
                pane_ids_before.add(existing_pane_id)
        cmd = self.action_command(action_session, "new-pane")
        if cwd:
            cmd.extend(["--cwd", resolved_cwd])
        cmd.extend(["--name", pane_name])
        if tab_id is not None:
            cmd.extend(["--tab-id", str(tab_id)])
        if command:
            cmd.append("--")
            cmd.extend(command)

        result = self._run(cmd, timeout=10, cwd=resolved_cwd)
        if result is None:
            pane_id = None
        elif result.returncode != 0:
            return None
        else:
            pane_id = self._extract_created_pane_id(result.stdout)
        if pane_id is None:
            pane_id = self._wait_for_created_pane(
                action_session,
                pane_ids_before,
                pane_name,
                tab_id,
                allow_unnamed=bool(panes_before),
            )
        return WorkspaceRef(
            resource_type="pane",
            session=report_session or "unknown",
            pane=pane_id,
        )

    def _wait_for_created_pane(
        self,
        session: Optional[str],
        pane_ids_before: Set[str],
        pane_name: str,
        tab_id: Optional[int],
        allow_unnamed: bool,
    ) -> str:
        """Resolve one asynchronously created terminal pane without guessing."""
        saw_discovery = False
        for _unused_attempt in range(40):
            panes_after = self.list_panes_checked(session, include_plugins=True)
            if panes_after is not None:
                saw_discovery = True
                new_terminal_panes = [
                    pane
                    for pane in panes_after
                    if not pane.get("is_plugin")
                    and pane.get("pane_id") not in pane_ids_before
                    and (tab_id is None or pane.get("tab_id") == tab_id)
                ]
                named_panes = [
                    pane
                    for pane in new_terminal_panes
                    if pane.get("title") == pane_name
                ]
                candidates = named_panes
                if not candidates and allow_unnamed:
                    candidates = new_terminal_panes
                if len(candidates) == 1:
                    pane_id = candidates[0].get("pane_id")
                    if isinstance(pane_id, str) and pane_id:
                        return pane_id
                    raise ZellijMutationOutcomeUnknownError(
                        "created pane identity is invalid"
                    )
                if len(candidates) > 1:
                    raise ZellijMutationOutcomeUnknownError(
                        "created pane identity is ambiguous"
                    )
            time.sleep(0.05)
        message = (
            "created pane identity is ambiguous"
            if saw_discovery
            else "created pane could not be discovered"
        )
        raise ZellijMutationOutcomeUnknownError(message)

    def _extract_created_pane_id(self, text: str) -> Optional[str]:
        """Extract the pane id returned by zellij new-pane/run."""
        match = re.search(r"\b(?:terminal|plugin)_\d+\b", text)
        if match:
            return match.group(0)
        text = text.strip()
        if text.isdigit():
            return f"terminal_{text}"
        return None

    def close_startup_plugin_panes(self, session: str) -> None:
        """Best-effort cleanup of zellij startup plugin panes."""
        panes = self.list_panes_checked(session, include_plugins=True)
        if panes is None:
            return
        for pane in panes:
            pane_id = pane.get("pane_id")
            if pane.get("is_plugin") and isinstance(pane_id, str):
                self.close_pane(pane_id, session=session)

    def close_pane(self, pane_id: Optional[str] = None, session: Optional[str] = None) -> bool:
        """Close a specific zellij pane."""
        if not pane_id or not self.is_available():
            return False
        result = self._run(
            self.action_command(session, "close-pane") + ["-p", pane_id],
            timeout=5,
        )
        if result and result.returncode == 0:
            return True

        target_session = session or self.get_current_session()
        sessions = self._list_sessions_checked()
        if target_session and sessions is not None and target_session not in sessions:
            return True
        panes = self.list_panes_checked(target_session, include_plugins=True)
        if panes is None:
            return False
        return bool(panes) and pane_id not in {
            pane.get("pane_id") for pane in panes
        }

    def close_session(self, session: str) -> bool:
        """Close a zellij session."""
        if not self.is_available():
            return False
        result = self._run(self._cmd("delete-session", "-f", session), timeout=5)
        if result and result.returncode == 0:
            return True
        sessions = self._list_sessions_checked()
        return sessions is not None and session not in sessions

    def write_to_pane(
        self,
        text: str,
        pane_id: Optional[str] = None,
        session: Optional[str] = None,
        enter: bool = False,
    ) -> bool:
        """Write literal text directly to a selected terminal pane."""
        if not pane_id or not self.is_available():
            return False
        if text:
            result = self._run(
                self.action_command(session, "write-chars")
                + ["-p", pane_id, "--", text],
                timeout=5,
            )
            if result is None or result.returncode != 0:
                return False
        if enter:
            return self.send_keys("Enter", pane_id=pane_id, session=session)
        return True

    def send_keys(
        self,
        keys: Union[str, List[str]],
        pane_id: Optional[str] = None,
        session: Optional[str] = None,
    ) -> bool:
        """Send zellij key names to a specific pane."""
        if not pane_id or not self.is_available():
            return False
        key_specs = keys if isinstance(keys, list) else [keys]
        key_args = [self.KEY_NAMES.get(key, key) for key in key_specs]
        if not key_args:
            return True
        result = self._run(
            self.action_command(session, "send-keys") + ["-p", pane_id] + key_args,
            timeout=5,
        )
        return bool(result and result.returncode == 0)

    def capture_pane(
        self,
        pane_id: Optional[str] = None,
        session: Optional[str] = None,
        full: bool = False,
        ansi: bool = False,
        max_bytes: int = 1024 * 1024 + 4,
    ) -> Optional[Dict[str, Any]]:
        """Dump a bounded tail of pane content without capturing full scrollback in memory."""
        if not pane_id or not self.is_available():
            return None
        try:
            with tempfile.TemporaryDirectory(prefix="zellij-mcp-screen-") as directory:
                dump_path = os.path.join(directory, "screen.txt")
                cmd = self.action_command(session, "dump-screen")
                if full:
                    cmd.append("-f")
                if ansi:
                    cmd.append("-a")
                cmd.extend(["-p", pane_id, "--path", dump_path])

                result = self._run(cmd, timeout=5)
                if (
                    result is None
                    or result.returncode != 0
                    or not os.path.isfile(dump_path)
                ):
                    return None
                size = os.path.getsize(dump_path)
                start = max(0, size - max_bytes)
                with open(dump_path, "rb") as handle:
                    handle.seek(start)
                    content = handle.read(max_bytes)
                return {
                    "text": content.decode("utf-8", errors="replace"),
                    "truncated": start > 0,
                }
        except OSError:
            return None

    def list_panes_checked(
        self,
        session: Optional[str] = None,
        include_plugins: bool = False,
    ) -> Optional[List[Dict[str, Any]]]:
        """List panes without collapsing command failure into an empty session."""
        if not self.is_available():
            return None
        if not session and not self.is_inside_zellij():
            return None

        result = self._run(
            self.action_command(session, "list-panes")
            + ["--json", "--command", "--state", "--tab", "--geometry"],
            timeout=5,
        )
        if result is None or result.returncode != 0:
            return None
        try:
            payload = json.loads(result.stdout)
        except (TypeError, ValueError):
            return None
        panes = self._normalize_panes(payload)
        if not panes and payload != [] and not self._payload_has_empty_panes(payload):
            return None
        if include_plugins:
            return panes
        return [pane for pane in panes if not pane["is_plugin"]]

    def _payload_has_empty_panes(self, payload: Any) -> bool:
        """Recognize known pane containers that explicitly contain no panes."""
        return self._discovery.payload_has_empty_panes(payload)

    def get_session_summary(
        self,
        session: Optional[str] = None,
        include_plugins: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Return live pane counts and normalized pane metadata for one session."""
        target_session = session or self.get_current_session()
        if not target_session:
            return None

        all_panes = self.list_panes_checked(target_session, include_plugins=True)
        if all_panes is None or not all_panes:
            return None
        terminal_panes = [pane for pane in all_panes if not pane["is_plugin"]]
        plugin_panes = [pane for pane in all_panes if pane["is_plugin"]]
        visible_panes = all_panes if include_plugins else terminal_panes
        current_session = self.get_current_session()
        current_pane = self.get_current_pane_id()
        panes = []  # type: List[Dict[str, Any]]

        for pane in visible_panes:
            pane_info = dict(pane)
            pane_info["is_current"] = bool(
                target_session == current_session and pane_info["pane_id"] == current_pane
            )
            panes.append(pane_info)

        return {
            "session": target_session,
            "is_current": target_session == current_session,
            "total_pane_count": len(all_panes),
            "pane_count": len(terminal_panes),
            "terminal_pane_count": len(terminal_panes),
            "plugin_pane_count": len(plugin_panes),
            "panes": panes,
        }

    def _normalize_panes(self, payload: Any) -> List[Dict[str, Any]]:
        """Normalize zellij's JSON pane output across versions."""
        return self._discovery.normalize_panes(payload)

    def _looks_like_pane(self, value: Dict[str, Any]) -> bool:
        """Avoid treating nested tab or geometry dictionaries as panes."""
        return self._discovery.looks_like_pane(value)

    def _pane_id_from_dict(self, value: Dict[str, Any]) -> Optional[str]:
        return self._discovery.pane_id_from_dict(value)

    def _first_text(self, value: Dict[str, Any], *keys: str) -> str:
        return self._discovery.first_text(value, *keys)

    def _text_value(self, value: Any) -> str:
        return self._discovery.text_value(value)

    def _pane_state(self, value: Dict[str, Any]) -> str:
        return self._discovery.pane_state(value)

    def _pane_sort_key(self, pane: Dict[str, Any]) -> Any:
        return self._discovery.pane_sort_key(pane)

    def normalize_pane_id(self, pane_id: str, is_plugin: bool = False) -> str:
        """Normalize numeric pane ids to zellij terminal_<id> form."""
        return self._discovery.normalize_pane_id(pane_id, is_plugin=is_plugin)

    def doctor(self) -> Dict[str, Any]:
        """Run zellij doctor check."""
        result: Dict[str, Any] = {
            "available": self.is_available(),
            "running": self.is_running(),
            "inside_zellij": self.is_inside_zellij(),
            "current_session": self.get_current_session(),
            "current_pane": self.get_current_pane_id(),
            "current_workspace": None,
            "supports_background_create": False,
            "supports_stable_tab_control": False,
            "supports_direct_pane_io": False,
            "version": None,
            "sessions": [],
            "warnings": [],
            "fixes": [],
        }

        if not self.is_available():
            result["warnings"].append("zellij not found in PATH")
            result["fixes"].append(
                "Install zellij separately, add it to PATH, and rerun zellij-mcp doctor"
            )
            return result

        version_result = self._run(self._cmd("--version"), timeout=5)
        if version_result and version_result.returncode == 0:
            result["version"] = version_result.stdout.strip()
        else:
            result["warnings"].append("Failed to get zellij version")

        result["supports_background_create"] = self.supports_background_create()
        if not result["supports_background_create"]:
            result["warnings"].append("zellij attach --create-background is not supported")
            result["fixes"].append("Upgrade zellij or use current-session pane mode")

        result["supports_stable_tab_control"] = self.supports_stable_tab_control()
        if not result["supports_stable_tab_control"]:
            result["warnings"].append(
                "zellij stable Tab actions or new-pane --tab-id are not supported"
            )
            result["fixes"].append("Upgrade zellij separately and rerun doctor")

        result["supports_direct_pane_io"] = self.supports_direct_pane_io()
        if not result["supports_direct_pane_io"]:
            result["warnings"].append(
                "zellij direct write-chars/send-keys/dump-screen is not supported"
            )
            result["fixes"].append("Upgrade zellij separately and rerun doctor")

        result["sessions"] = self.list_sessions()
        if result["current_session"]:
            result["current_workspace"] = self.get_session_summary(
                result["current_session"],
                include_plugins=False,
            )
        return result
