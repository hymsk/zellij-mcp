#!/usr/bin/env python3
"""Verify direct-pane current/plugin/unknown close protection through MCP."""

import json
import sys
import time

from zellij_pane_lifecycle import (
    MCPClient,
    ProbeError,
    default_server_command,
    terminal_pane_ids,
)


def run_probe(command):
    """Require destructive pane operations to resolve and fail closed."""
    client = MCPClient(command)
    started_at = time.time()
    try:
        doctor, unused_error = client.tool("zellij_mcp_doctor", {})
        zellij = doctor.get("zellij", {})
        session_name = zellij.get("current_session")
        current_pane = zellij.get("current_pane")
        if not session_name or not current_pane:
            raise ProbeError("doctor returned no current zellij pane identity")

        listed, unused_error = client.tool("workspace_list", {
            "session_name": session_name,
            "include_plugins": True,
        })
        baseline = terminal_pane_ids(listed, session_name)
        session = next(
            item
            for item in listed.get("sessions", [])
            if item.get("session") == session_name
        )
        plugin_panes = [
            item.get("pane_id")
            for item in session.get("panes", [])
            if item.get("is_plugin") and item.get("pane_id")
        ]
        if current_pane not in baseline:
            raise ProbeError("current MCP pane is absent from workspace_list")

        refused, is_error = client.tool("pane_close", {
            "session_name": session_name,
            "pane_id": current_pane,
            "force": True,
        }, True)
        if not is_error or refused.get("code") != "permission_denied":
            raise ProbeError("pane_close did not reject the current MCP pane")

        missing, is_error = client.tool("pane_close", {
            "session_name": session_name,
            "pane_id": "terminal_2147483647",
            "force": True,
        }, True)
        if not is_error or missing.get("code") != "workspace_not_found":
            raise ProbeError("pane_close did not reject an unknown pane")

        plugin_code = None
        if plugin_panes:
            plugin, is_error = client.tool("pane_close", {
                "session_name": session_name,
                "pane_id": plugin_panes[0],
                "force": True,
            }, True)
            plugin_code = plugin.get("code")
            if not is_error or plugin_code != "permission_denied":
                raise ProbeError("pane_close did not reject a plugin pane")

        after, unused_error = client.tool("workspace_list", {
            "session_name": session_name,
            "include_plugins": True,
        })
        if terminal_pane_ids(after, session_name) != baseline:
            raise ProbeError("failed pane_close calls changed the pane baseline")

        return {
            "ok": True,
            "server_command": command,
            "session_name": session_name,
            "current_pane": current_pane,
            "refusal_code": refused.get("code"),
            "missing_code": missing.get("code"),
            "plugin_code": plugin_code,
            "pane_count": len(baseline),
            "elapsed_seconds": round(time.time() - started_at, 3),
        }
    finally:
        client.close()


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
