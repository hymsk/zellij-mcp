#!/usr/bin/env python3
"""Run a real stable-Tab lifecycle through the direct-pane MCP surface."""

import json
import os
import sys
import time
import uuid

from zellij_pane_lifecycle import (
    MCPClient,
    ProbeError,
    cleanup_with_mcp,
    default_server_command,
)


def session_payload(payload, session_name):
    """Return one session from a tab_list payload."""
    sessions = [
        item
        for item in payload.get("sessions", [])
        if item.get("session") == session_name
    ]
    if len(sessions) != 1:
        raise ProbeError("tab_list did not return the expected session")
    return sessions[0]


def tab_payload(payload, session_name, tab_id):
    """Return one stable Tab from a tab_list payload."""
    tabs = [
        item
        for item in session_payload(payload, session_name).get("tabs", [])
        if item.get("tab_id") == tab_id
    ]
    if len(tabs) != 1:
        raise ProbeError("tab_list did not return stable Tab ID {}".format(tab_id))
    return tabs[0]


def run_probe(command, environment=None, working_directory=None):
    """Create, route, rename and close a unique Tab and its direct panes."""
    unique = uuid.uuid4().hex[:12]
    session_name = "zellij-mcp-tab-e2e-{}-{}".format(os.getpid(), unique)
    root_pane_id = None
    routed_pane_id = None
    tab_id = None
    original_tab_id = None
    root_closed = False
    client = MCPClient(command, environment, working_directory)
    started_at = time.time()
    try:
        tools_result = client.call("tools/list", {})
        tool_names = {item.get("name") for item in tools_result.get("tools", [])}
        required = {
            "workspace_create",
            "tab_list",
            "tab_focus",
            "tab_rename",
            "tab_close",
            "pane_close",
        }
        if not required.issubset(tool_names):
            raise ProbeError("MCP tools/list is missing Tab or direct-pane controls")

        root, unused_error = client.tool("workspace_create", {
            "request_id": "tab-root-{}".format(unique),
            "command": ["/bin/sh", "-c", "while :; do sleep 60; done"],
            "workspace_type": "new-session",
            "session_name": session_name,
        })
        root_pane_id = root.get("pane_id")
        if root.get("session") != session_name or not root_pane_id:
            raise ProbeError("workspace_create returned no root pane identity")

        initial, unused_error = client.tool("tab_list", {
            "session_name": session_name,
        })
        initial_session = session_payload(initial, session_name)
        initial_tabs = initial_session.get("tabs", [])
        if initial_session.get("tab_count") != 1 or len(initial_tabs) != 1:
            raise ProbeError("unique session did not start with one Tab")
        original_tab_id = initial_tabs[0].get("tab_id")
        if not isinstance(original_tab_id, int):
            raise ProbeError("unique session returned no stable original Tab ID")

        created, unused_error = client.tool("workspace_create", {
            "request_id": "tab-create-{}".format(unique),
            "session_name": session_name,
            "tab_name": "Build {}".format(unique),
            "command": ["/bin/sh", "-c", "while :; do sleep 60; done"],
            "workspace_type": "new-tab",
            "focus": False,
            "return_tab_id": original_tab_id,
        })
        tab_id = created.get("tab_id")
        if not isinstance(tab_id, int):
            raise ProbeError("workspace_create(new-tab) returned no stable Tab ID")
        if created.get("focus_restored") is False:
            raise ProbeError("workspace_create(new-tab) reported a focus restoration mismatch")

        routed, unused_error = client.tool("workspace_create", {
            "request_id": "tab-pane-{}".format(unique),
            "command": ["/bin/sh", "-c", "while :; do sleep 60; done"],
            "workspace_type": "new-pane",
            "session_name": session_name,
            "tab_id": tab_id,
            "focus": False,
            "return_tab_id": original_tab_id,
        })
        routed_pane_id = routed.get("pane_id")
        if routed.get("tab_id") != tab_id or not routed_pane_id:
            raise ProbeError("workspace_create returned the wrong target Tab")

        focused, unused_error = client.tool("tab_focus", {
            "session_name": session_name,
            "tab_id": tab_id,
        })
        if focused.get("focus_verified") is False:
            raise ProbeError("tab_focus reported a known target mismatch")

        renamed_name = "Routed {}".format(unique)
        renamed, unused_error = client.tool("tab_rename", {
            "session_name": session_name,
            "tab_id": tab_id,
            "tab_name": renamed_name,
        })
        if not renamed.get("verified"):
            raise ProbeError("tab_rename did not verify the new name")

        listed, unused_error = client.tool("tab_list", {
            "session_name": session_name,
            "include_panes": True,
        })
        routed_tab = tab_payload(listed, session_name, tab_id)
        if routed_tab.get("name") != renamed_name:
            raise ProbeError("tab_list lost the renamed Tab identity")
        if routed_pane_id not in {
            item.get("pane_id") for item in routed_tab.get("panes", [])
        }:
            raise ProbeError("routed pane was not listed in the requested Tab")

        closed_tab, unused_error = client.tool("tab_close", {
            "session_name": session_name,
            "tab_id": tab_id,
            "force": True,
        })
        if not closed_tab.get("closed") or not closed_tab.get("verified"):
            raise ProbeError("tab_close did not verify the destructive operation")

        remaining, unused_error = client.tool("tab_list", {
            "session_name": session_name,
        })
        remaining_session = session_payload(remaining, session_name)
        if remaining_session.get("tab_count") != 1:
            raise ProbeError("tab_close did not leave exactly the original Tab")
        if remaining_session.get("active_tab_id") not in (None, original_tab_id):
            raise ProbeError("tab_close changed the surviving active Tab")

        root_close, unused_error = client.tool("tab_close", {
            "session_name": session_name,
            "tab_id": original_tab_id,
            "force": True,
        })
        if not root_close.get("closed") or not root_close.get("verified"):
            raise ProbeError("tab_close did not close the original Tab")
        root_closed = True

        missing, is_error = client.tool("tab_list", {
            "session_name": session_name,
        }, True)
        if not is_error or missing.get("code") != "workspace_not_found":
            raise ProbeError("closed Tab session is still discoverable")

        return {
            "ok": True,
            "server_command": command,
            "tool_count": len(tool_names),
            "session_name": session_name,
            "root_pane_id": root_pane_id,
            "routed_pane_id": routed_pane_id,
            "tab_id": tab_id,
            "elapsed_seconds": round(time.time() - started_at, 3),
        }
    finally:
        close_error = None
        try:
            client.close()
        except Exception as exc:
            close_error = exc
        if not root_closed:
            cleanup_with_mcp(
                command,
                session_name,
                root_pane_id,
                original_tab_id,
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
