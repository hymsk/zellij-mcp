#!/usr/bin/env python3
"""Run a real direct-pane lifecycle exclusively through MCP stdio calls."""

import json
import os
import select
import subprocess
import sys
import time
import uuid
from contextlib import suppress

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ProbeError(RuntimeError):
    """Raised when the MCP lifecycle contract is not satisfied."""


class MCPClient:
    """Minimal newline-delimited MCP stdio client for integration probes."""

    def __init__(self, command, environment=None, working_directory=None):
        self.command = list(command)
        self.environment = dict(environment) if environment is not None else None
        self.working_directory = working_directory or PROJECT_ROOT
        self.next_id = 1
        self.process = subprocess.Popen(
            self.command,
            cwd=self.working_directory,
            env=self.environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
        )
        self.call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "zellij-mcp-pane-probe", "version": "1"},
        })
        self.notify("notifications/initialized", {})

    def call(self, method, params, timeout=15):
        request_id = self.next_id
        self.next_id += 1
        self._write({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        })
        response = self._read(timeout)
        if response.get("id") != request_id:
            raise ProbeError("MCP response id mismatch")
        if "error" in response:
            raise ProbeError("MCP JSON-RPC error: {}".format(response["error"]))
        return response["result"]

    def notify(self, method, params):
        self._write({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        })

    def tool(self, name, arguments, allow_error=False):
        result = self.call("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        payload = result.get("structuredContent")
        if not isinstance(payload, dict):
            raise ProbeError("MCP tool returned no structured content: {}".format(name))
        if result.get("isError") and not allow_error:
            raise ProbeError("MCP tool {} failed: {}".format(name, payload))
        return payload, bool(result.get("isError"))

    def close(self):
        if self.process.stdin:
            with suppress(OSError):
                self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        stderr = self.process.stderr.read() if self.process.stderr else ""
        if stderr.strip():
            raise ProbeError("MCP server wrote stderr: {}".format(stderr.strip()))

    def _write(self, value):
        if self.process.poll() is not None or self.process.stdin is None:
            raise ProbeError("MCP server exited before request")
        self.process.stdin.write(json.dumps(value, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def _read(self, timeout):
        if self.process.stdout is None:
            raise ProbeError("MCP server stdout is unavailable")
        ready, unused_write, unused_error = select.select(
            [self.process.stdout],
            [],
            [],
            timeout,
        )
        if not ready:
            raise ProbeError("Timed out waiting for MCP response")
        line = self.process.stdout.readline()
        if not line:
            stderr = self.process.stderr.read() if self.process.stderr else ""
            raise ProbeError("MCP server closed stdout: {}".format(stderr.strip()))
        try:
            return json.loads(line)
        except ValueError as exc:
            raise ProbeError(
                "MCP server emitted non-JSON stdout: {}".format(exc)
            ) from exc


def default_server_command():
    """Use source by default; positional arguments can select an installed wrapper."""
    if len(sys.argv) > 1:
        return sys.argv[1:]
    return [sys.executable, "-m", "zellij_mcp", "serve"]


def session_payload(payload, session_name):
    """Return one exact workspace_list session payload."""
    sessions = [
        item
        for item in payload.get("sessions", [])
        if item.get("session") == session_name
    ]
    if len(sessions) != 1:
        raise ProbeError("workspace_list did not return the expected session")
    return sessions[0]


def terminal_pane_ids(payload, session_name):
    """Return terminal pane IDs from one exact workspace_list session."""
    return {
        item.get("pane_id")
        for item in session_payload(payload, session_name).get("panes", [])
        if item.get("pane_id") and not item.get("is_plugin")
    }


def cleanup_with_mcp(
    command,
    session_name,
    pane_id,
    tab_id=None,
    environment=None,
    working_directory=None,
):
    """Best-effort exact direct-pane cleanup through a fresh MCP process."""
    if not session_name or (not pane_id and tab_id is None):
        return
    client = MCPClient(command, environment, working_directory)
    try:
        if tab_id is not None:
            client.tool("tab_close", {
                "session_name": session_name,
                "tab_id": tab_id,
                "force": True,
            }, True)
        else:
            client.tool("pane_close", {
                "session_name": session_name,
                "pane_id": pane_id,
                "force": True,
            }, True)
    finally:
        client.close()


def run_probe(command, environment=None, working_directory=None):
    """Create, write, capture and remove one pane via the public pane identity."""
    unique = uuid.uuid4().hex[:12]
    session_name = "zellij-mcp-pane-e2e-{}-{}".format(os.getpid(), unique)
    marker = "ZELLIJ_MCP_DIRECT_PANE_{}".format(unique)
    root_pane_id = None
    pane_id = None
    tab_id = None
    closed = False
    client = MCPClient(command, environment, working_directory)
    started_at = time.time()
    probe_cwd = working_directory or PROJECT_ROOT
    try:
        tools_result = client.call("tools/list", {})
        tool_names = {item.get("name") for item in tools_result.get("tools", [])}
        required = {
            "workspace_create",
            "workspace_list",
            "pane_write_text",
            "pane_send_key",
            "pane_screen",
            "pane_close",
            "tab_close",
        }
        if not required.issubset(tool_names):
            raise ProbeError("MCP tools/list is missing direct-pane tools")

        doctor, unused_error = client.tool("zellij_mcp_doctor", {})
        if not doctor.get("ok"):
            raise ProbeError("zellij_mcp_doctor rejected the isolated runtime")

        created, unused_error = client.tool("workspace_create", {
            "request_id": "pane-create-{}".format(unique),
            "command": ["/bin/sh", "-c", "while :; do sleep 60; done"],
            "cwd": probe_cwd,
            "workspace_type": "new-session",
            "session_name": session_name,
        })
        root_pane_id = created.get("pane_id")
        tab_id = created.get("tab_id")
        if created.get("session") != session_name or not root_pane_id:
            raise ProbeError("workspace_create returned an invalid pane identity")

        target, unused_error = client.tool("workspace_create", {
            "request_id": "pane-target-{}".format(unique),
            "command": ["/bin/sh"],
            "cwd": probe_cwd,
            "workspace_type": "new-pane",
            "session_name": session_name,
        })
        pane_id = target.get("pane_id")
        if target.get("session") != session_name or not pane_id:
            raise ProbeError("workspace_create returned no target pane identity")

        listed, unused_error = client.tool("workspace_list", {
            "session_name": session_name,
            "include_plugins": True,
        })
        if pane_id not in terminal_pane_ids(listed, session_name):
            raise ProbeError("workspace_list did not return the created pane")

        client.tool("pane_write_text", {
            "session_name": session_name,
            "pane_id": pane_id,
            "text": "printf '{}\\n'".format(marker),
        })
        client.tool("pane_send_key", {
            "session_name": session_name,
            "pane_id": pane_id,
            "key": "Enter",
        })

        deadline = time.time() + 5.0
        screen = None
        while time.time() < deadline:
            screen, unused_error = client.tool("pane_screen", {
                "session_name": session_name,
                "pane_id": pane_id,
                "full": True,
            })
            if marker in screen.get("text", ""):
                break
            time.sleep(0.05)
        if not screen or marker not in screen.get("text", ""):
            raise ProbeError("pane_screen did not observe direct pane input")

        closed_payload, unused_error = client.tool("pane_close", {
            "session_name": session_name,
            "pane_id": pane_id,
            "force": True,
        })
        if not closed_payload.get("closed") or not closed_payload.get("verified"):
            raise ProbeError("pane_close did not verify the destructive operation")
        if closed_payload.get("session_closed"):
            raise ProbeError("pane_close unexpectedly deleted the whole session")
        if not isinstance(tab_id, int):
            raise ProbeError("pane_close left a session without a stable Tab ID")
        tab_cleanup, unused_error = client.tool("tab_close", {
            "session_name": session_name,
            "tab_id": tab_id,
            "force": True,
        })
        if not tab_cleanup.get("closed") or not tab_cleanup.get("verified"):
            raise ProbeError("tab_close did not clean the surviving session")
        closed = True

        missing, is_error = client.tool("workspace_list", {
            "session_name": session_name,
        }, True)
        if not is_error or missing.get("code") != "workspace_not_found":
            raise ProbeError("cleaned pane session is still discoverable")

        return {
            "ok": True,
            "server_command": command,
            "tool_count": len(tool_names),
            "session_name": session_name,
            "root_pane_id": root_pane_id,
            "pane_id": pane_id,
            "elapsed_seconds": round(time.time() - started_at, 3),
        }
    finally:
        close_error = None
        try:
            client.close()
        except Exception as exc:
            close_error = exc
        if not closed:
            cleanup_with_mcp(
                command,
                session_name,
                pane_id,
                tab_id,
                environment,
                working_directory,
            )
        if close_error is not None:
            raise close_error


def main():
    """Run the probe and print one machine-readable result."""
    command = default_server_command()
    try:
        result = run_probe(command)
    except Exception as exc:
        print(json.dumps({
            "ok": False,
            "server_command": command,
            "error": str(exc),
        }, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
