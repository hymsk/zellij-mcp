"""Direct-pane contract tests for the Zellij MCP server."""

import asyncio
import json

import pytest

from zellij_mcp.core.types import ErrorCode, WorkspaceRef
from zellij_mcp.server.main import ZellijMCPServer

PUBLIC_TOOLS = (
    "zellij_mcp_doctor",
    "workspace_create",
    "workspace_list",
    "tab_list",
    "tab_focus",
    "tab_rename",
    "tab_close",
    "pane_write_text",
    "pane_send_key",
    "pane_screen",
    "pane_close",
)
EXPECTED_ANNOTATIONS = {
    "zellij_mcp_doctor": (True, False, True, False),
    "workspace_create": (False, True, False, True),
    "workspace_list": (True, False, True, False),
    "tab_list": (True, False, True, False),
    "tab_focus": (False, False, True, False),
    "tab_rename": (False, False, True, False),
    "tab_close": (False, True, False, True),
    "pane_write_text": (False, True, False, True),
    "pane_send_key": (False, True, False, True),
    "pane_screen": (True, False, True, False),
    "pane_close": (False, True, False, True),
}


def run_async(coro):
    """Run one coroutine without requiring a pytest asyncio plugin."""
    return asyncio.get_event_loop().run_until_complete(coro)


def pane(
    pane_id,
    tab_id=0,
    plugin=False,
    focused=False,
    title=None,
):
    """Build normalized live pane metadata."""
    return {
        "pane_id": pane_id,
        "is_plugin": plugin,
        "is_focused": focused,
        "is_fullscreen": False,
        "is_floating": False,
        "is_suppressed": plugin,
        "is_held": False,
        "is_selectable": True,
        "exited": False,
        "exit_status": None,
        "title": title or pane_id,
        "command": "" if plugin else "/bin/bash",
        "cwd": "/work",
        "state": "suppressed" if plugin else "running",
        "tab_id": tab_id,
        "tab_position": tab_id,
        "tab_name": "Tab #{}".format(tab_id + 1),
        "pane_x": 0,
        "pane_y": 0,
        "pane_rows": 24,
        "pane_columns": 80,
        "pane_content_rows": 23,
        "pane_content_columns": 80,
    }


def tab(tab_id, active=False, name=None):
    """Build normalized stable Tab metadata."""
    return {
        "tab_id": tab_id,
        "position": tab_id,
        "name": name or "Tab #{}".format(tab_id + 1),
        "active": active,
        "active_source": "native" if active else "unavailable",
        "is_fullscreen_active": False,
        "is_sync_panes_active": False,
        "are_floating_panes_visible": False,
        "selectable_tiled_panes_count": 1,
        "selectable_floating_panes_count": 0,
        "viewport_rows": 24,
        "viewport_columns": 80,
        "display_area_rows": 25,
        "display_area_columns": 80,
        "has_bell_notification": False,
        "is_flashing_bell": False,
    }


class FakeZellijDriver:
    """Stateful direct-pane fake matching the public server dependencies."""

    def __init__(self, inside=True):
        self.available = True
        self.inside = inside
        self.current_session = "main" if inside else None
        self.current_pane = "terminal_0" if inside else None
        self.sessions_available = True
        self.panes_available = True
        self.tabs_available = True
        self.session_panes = {}
        self.session_tabs = {}
        self.created_panes = []
        self.created_sessions = []
        self.created_tabs = []
        self.focused_tabs = []
        self.renamed_tabs = []
        self.closed_tabs = []
        self.writes = []
        self.keys = []
        self.captures = []
        self.closed_panes = []
        self.closed_sessions = []
        self.close_breaks_session_discovery = False
        self.screens = {}
        if inside:
            self.add_session("main", current=True)

    def add_session(self, session, current=False):
        self.session_panes[session] = [
            pane("terminal_0", focused=current),
            pane("terminal_1"),
            pane("plugin_0", plugin=True),
        ]
        self.session_tabs[session] = [tab(0, active=True)]
        self.screens[(session, "terminal_0")] = "$ "
        self.screens[(session, "terminal_1")] = "ready\n$ "
        if current:
            self.current_session = session
            self.current_pane = "terminal_0"

    def is_available(self):
        return self.available

    def supports_background_create(self):
        return True

    def supports_stable_tab_control(self):
        return True

    def is_inside_zellij(self):
        return self.inside

    def get_current_session(self):
        return self.current_session

    def get_current_pane_id(self):
        return self.current_pane

    def normalize_pane_id(self, pane_id, is_plugin=False):
        value = pane_id.strip()
        if value.isdigit():
            return "{}_{}".format("plugin" if is_plugin else "terminal", value)
        return value

    def list_sessions(self):
        sessions = self.list_sessions_checked()
        return sessions if sessions is not None else []

    def list_sessions_checked(self):
        if not self.sessions_available:
            return None
        return list(self.session_panes)

    def session_presence(self, session):
        if not self.sessions_available:
            return None
        return session in self.session_panes

    def list_panes_checked(self, session=None, include_plugins=False):
        if not self.panes_available:
            return None
        return self.list_panes(session, include_plugins=include_plugins)

    def list_panes(self, session=None, include_plugins=False):
        if not self.panes_available:
            return []
        target = session or self.current_session
        panes = [dict(item) for item in self.session_panes.get(target, [])]
        if include_plugins:
            return panes
        return [item for item in panes if not item["is_plugin"]]

    def get_session_summary(self, session=None, include_plugins=False):
        if not self.panes_available:
            return None
        target = session or self.current_session
        if target not in self.session_panes:
            return None
        all_panes = self.list_panes(target, include_plugins=True)
        terminals = [item for item in all_panes if not item["is_plugin"]]
        plugins = [item for item in all_panes if item["is_plugin"]]
        visible = all_panes if include_plugins else terminals
        for item in visible:
            item["is_current"] = bool(
                target == self.current_session
                and item["pane_id"] == self.current_pane
            )
        return {
            "session": target,
            "is_current": target == self.current_session,
            "total_pane_count": len(all_panes),
            "pane_count": len(terminals),
            "terminal_pane_count": len(terminals),
            "plugin_pane_count": len(plugins),
            "panes": visible,
        }

    def list_tabs_checked(self, session=None):
        if not self.tabs_available:
            return None
        target = session or self.current_session
        return [dict(item) for item in self.session_tabs.get(target, [])]

    def create_pane(self, session=None, cwd=None, command=None, tab_id=None):
        target = session or self.current_session
        if target not in self.session_panes:
            return None
        pane_id = "terminal_{}".format(
            max(
                [
                    int(item["pane_id"].split("_", 1)[1])
                    for item in self.session_panes[target]
                    if item["pane_id"].startswith("terminal_")
                ]
            )
            + 1
        )
        target_tab = tab_id if tab_id is not None else 0
        self.session_panes[target].append(pane(pane_id, tab_id=target_tab))
        self.screens[(target, pane_id)] = "$ "
        self.created_panes.append({
            "session": target,
            "cwd": cwd,
            "command": command,
            "tab_id": tab_id,
            "pane_id": pane_id,
        })
        return WorkspaceRef(resource_type="pane", session=target, pane=pane_id)

    def create_session_with_command(self, session, cwd=None, command=None):
        if session in self.session_panes:
            return self.create_pane(session=session, cwd=cwd, command=command)
        self.add_session(session)
        self.created_sessions.append({
            "session": session,
            "cwd": cwd,
            "command": command,
        })
        return WorkspaceRef(
            resource_type="session",
            session=session,
            pane="terminal_0",
        )

    def create_tab(self, session=None, name=None, cwd=None, command=None):
        target = session or self.current_session
        if target not in self.session_tabs:
            return None
        tabs = self.session_tabs[target]
        tab_id = max([item["tab_id"] for item in tabs] or [-1]) + 1
        for item in tabs:
            item["active"] = False
        tabs.append(tab(tab_id, active=True, name=name))
        pane_id = "terminal_{}".format(tab_id + 10)
        self.session_panes[target].append(pane(pane_id, tab_id=tab_id))
        self.created_tabs.append({
            "session": target,
            "tab_id": tab_id,
            "name": name,
            "cwd": cwd,
            "command": command,
        })
        return tab_id

    def focus_tab(self, session, tab_id):
        target = next(
            (item for item in self.session_tabs.get(session, []) if item["tab_id"] == tab_id),
            None,
        )
        if target is None:
            return False
        for item in self.session_tabs[session]:
            item["active"] = item is target
            item["active_source"] = "native" if item is target else "unavailable"
        self.focused_tabs.append((session, tab_id))
        return True

    def rename_tab(self, session, tab_id, name):
        target = next(
            (item for item in self.session_tabs.get(session, []) if item["tab_id"] == tab_id),
            None,
        )
        if target is None:
            return False
        target["name"] = name
        self.renamed_tabs.append((session, tab_id, name))
        return True

    def close_tab(self, session, tab_id):
        tabs = self.session_tabs.get(session, [])
        if not any(item["tab_id"] == tab_id for item in tabs):
            return False
        self.session_tabs[session] = [item for item in tabs if item["tab_id"] != tab_id]
        self.session_panes[session] = [
            item for item in self.session_panes[session] if item["tab_id"] != tab_id
        ]
        self.closed_tabs.append((session, tab_id))
        return True

    def write_to_pane(self, text, pane_id=None, session=None, enter=False):
        self.writes.append({
            "session": session,
            "pane_id": pane_id,
            "text": text,
            "enter": enter,
        })
        return True

    def send_keys(self, keys, pane_id=None, session=None):
        self.keys.append({
            "session": session,
            "pane_id": pane_id,
            "keys": keys,
        })
        return True

    def capture_pane(
        self,
        pane_id=None,
        session=None,
        full=False,
        ansi=False,
        max_bytes=None,
    ):
        self.captures.append({
            "session": session,
            "pane_id": pane_id,
            "full": full,
            "ansi": ansi,
        })
        text = self.screens.get((session, pane_id))
        if text is None:
            return None
        encoded = text.encode("utf-8")
        if max_bytes is not None and len(encoded) > max_bytes:
            encoded = encoded[-max_bytes:]
            return {
                "text": encoded.decode("utf-8", errors="replace"),
                "truncated": True,
            }
        return {"text": text, "truncated": False}

    def close_pane(self, pane_id=None, session=None):
        if session not in self.session_panes:
            return False
        before = len(self.session_panes[session])
        self.session_panes[session] = [
            item for item in self.session_panes[session] if item["pane_id"] != pane_id
        ]
        if len(self.session_panes[session]) == before:
            return False
        self.closed_panes.append((session, pane_id))
        if self.close_breaks_session_discovery:
            self.sessions_available = False
        return True

    def close_session(self, session):
        if session not in self.session_panes:
            return False
        self.closed_sessions.append(session)
        del self.session_panes[session]
        self.session_tabs.pop(session, None)
        return True


@pytest.fixture
def server():
    instance = ZellijMCPServer()
    instance.zellij = FakeZellijDriver()
    yield instance
    instance.close()


def result_of(server, name, arguments):
    """Call a tool and require its success wrapper."""
    response = run_async(server.call_tool(name, arguments))
    assert response.get("error") is not True, response
    return response["result"]


def error_of(server, name, arguments):
    """Call a tool and require its stable error wrapper."""
    response = run_async(server.call_tool(name, arguments))
    assert response.get("error") is True, response
    return response


def test_rpc_initialize_and_tools_list_expose_only_direct_pane_tools(server):
    initialized = run_async(server.handle_rpc_message({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-06-18"},
    }))
    listed = run_async(server.handle_rpc_message({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }))

    assert initialized["result"]["protocolVersion"] == "2025-06-18"
    assert initialized["result"]["capabilities"]["tools"] == {"listChanged": False}
    assert tuple(item["name"] for item in listed["result"]["tools"]) == PUBLIC_TOOLS


def test_rpc_initialize_delivers_concise_selection_guidance(server):
    response = run_async(server.handle_rpc_message({
        "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {},
    }))
    instructions = response["result"]["instructions"]
    for guidance in (
        "when the user requests zellij",
        "persistent interactive terminal",
        "background terminal task",
        "configured remote server",
        "Otherwise, prefer the Host's normal execution tools",
        "Discover existing resources before operating on them",
        "preserve user focus and unrelated work",
    ):
        assert guidance in instructions
    assert len(instructions) <= 360


@pytest.mark.parametrize("name,arguments", [
    ("workspace_list", {"session_name": "main"}),
    ("tab_list", {"session_name": "main"}),
    ("pane_screen", {"session_name": "main", "pane_id": "terminal_1"}),
])
def test_advertised_read_defaults_match_omitted_runtime_arguments(server, name, arguments):
    defaults = {
        key: schema["default"]
        for key, schema in server.tools[name]["inputSchema"]["properties"].items()
        if "default" in schema
    }
    assert result_of(server, name, arguments) == result_of(
        server, name, dict(defaults, **arguments),
    )
    assert server.zellij.focused_tabs == []


def test_rpc_tools_call_returns_structured_content(server):
    response = run_async(server.handle_rpc_message({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "pane_write_text",
            "arguments": {
                "session_name": "main",
                "pane_id": "terminal_1",
                "text": "status",
            },
        },
    }))

    payload = response["result"]
    assert payload["isError"] is False
    assert payload["content"][0]["type"] == "text"
    assert json.loads(payload["content"][0]["text"]) == payload["structuredContent"]


@pytest.mark.parametrize("request_id", [None, True, 1.5])
def test_rpc_rejects_invalid_request_ids(server, request_id):
    response = run_async(server.handle_rpc_message({
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/list",
        "params": {},
    }))

    assert response["error"]["code"] == -32600


def test_rpc_request_method_without_id_has_no_side_effect(server):
    response = run_async(server.handle_rpc_message({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "pane_write_text",
            "arguments": {
                "session_name": "main",
                "pane_id": "terminal_1",
                "text": "blocked",
            },
        },
    }))

    assert response is None
    assert server.zellij.writes == []


@pytest.mark.parametrize("params", [[], "bad", 1])
def test_rpc_rejects_non_object_params(server, params):
    response = run_async(server.handle_rpc_message({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/list",
        "params": params,
    }))
    assert response["error"]["code"] == -32602


def test_tool_schemas_are_bounded_and_use_direct_pane_identity(server):
    assert tuple(server.tools) == PUBLIC_TOOLS
    pane_write_text = server.tools["pane_write_text"]["inputSchema"]
    pane_send_key = server.tools["pane_send_key"]["inputSchema"]
    pane_screen = server.tools["pane_screen"]["inputSchema"]
    pane_close = server.tools["pane_close"]["inputSchema"]

    assert set(pane_write_text["properties"]) == {"session_name", "pane_id", "text"}
    assert set(pane_send_key["properties"]) == {"session_name", "pane_id", "key"}
    assert set(pane_screen["properties"]) == {"session_name", "pane_id", "full", "ansi"}
    assert set(pane_close["properties"]) == {"session_name", "pane_id", "force"}
    assert pane_write_text["required"] == ["session_name", "pane_id", "text"]
    assert pane_send_key["required"] == ["session_name", "pane_id", "key"]
    assert pane_screen["required"] == ["session_name", "pane_id"]
    assert pane_close["required"] == ["session_name", "pane_id"]
    for name in ("tab_focus", "tab_rename", "tab_close"):
        assert "session_name" in server.tools[name]["inputSchema"]["required"]
    assert pane_write_text["properties"]["text"]["maxLength"] == 64 * 1024
    assert "Ctrl-C" in pane_send_key["properties"]["key"]["enum"]
    assert "Ctrl-Alt-Delete" not in pane_send_key["properties"]["key"]["enum"]
    for tool in server.tools.values():
        schema = tool["inputSchema"]
        assert schema["additionalProperties"] is False


def test_tools_list_exposes_explicit_behavior_annotations(server):
    for name, expected in EXPECTED_ANNOTATIONS.items():
        annotations = server.tools[name]["annotations"]
        assert (
            annotations["readOnlyHint"],
            annotations["destructiveHint"],
            annotations["idempotentHint"],
            annotations["openWorldHint"],
        ) == expected


def test_unknown_tool_and_unknown_fields_are_rejected(server):
    unknown_tool = error_of(server, "unknown_tool", {})
    unknown_field = error_of(server, "pane_screen", {
        "pane_id": "terminal_1",
        "unexpected": True,
    })

    assert unknown_tool["code"] == ErrorCode.INVALID_ARGUMENT.value
    assert unknown_field["code"] == ErrorCode.INVALID_ARGUMENT.value


def test_workspace_list_reports_terminal_and_plugin_counts(server):
    payload = result_of(server, "workspace_list", {
        "session_name": "main",
        "include_plugins": True,
    })

    assert payload["session_count"] == 1
    assert payload["total_pane_count"] == 3
    assert payload["pane_count"] == 2
    assert payload["terminal_pane_count"] == 2
    assert payload["plugin_pane_count"] == 1
    assert [item["pane_id"] for item in payload["sessions"][0]["panes"]] == [
        "terminal_0",
        "terminal_1",
        "plugin_0",
    ]


def test_workspace_list_fails_closed_when_session_discovery_is_unknown(server):
    server.zellij.sessions_available = False
    response = error_of(server, "workspace_list", {"all_sessions": True})

    assert response["code"] == ErrorCode.INTERNAL_ERROR.value
    assert response.get("result") is None


def test_workspace_create_launches_command_directly_in_existing_session(server):
    payload = result_of(server, "workspace_create", {
        "request_id": "create-pane",
        "command": ["bash", "-lc", "echo ready"],
        "cwd": "/work",
        "workspace_type": "new-pane",
        "session_name": "main",
    })

    assert payload["session"] == "main"
    assert payload["pane_id"].startswith("terminal_")
    assert server.zellij.created_panes == [{
        "session": "main",
        "cwd": "/work",
        "command": ["bash", "-lc", "echo ready"],
        "tab_id": None,
        "pane_id": payload["pane_id"],
    }]


def test_workspace_create_can_create_a_background_session(server):
    server.zellij = FakeZellijDriver(inside=False)
    payload = result_of(server, "workspace_create", {
        "request_id": "create-session",
        "command": ["bash"],
        "workspace_type": "new-session",
        "session_name": "build",
    })

    assert payload["session"] == "build"
    assert payload["pane_id"] == "terminal_0"
    assert payload["workspace_ref"] == {
        "type": "session",
        "session": "build",
        "pane": "terminal_0",
    }
    assert server.zellij.created_sessions[0]["command"] == ["bash"]


def test_workspace_create_new_tab_restores_the_requested_tab(server):
    payload = result_of(server, "workspace_create", {
        "request_id": "create-tab",
        "command": ["bash"],
        "workspace_type": "new-tab",
        "session_name": "main",
        "return_tab_id": 0,
    })

    assert payload["tab_id"] == 1
    assert payload["workspace_ref"] == {
        "type": "tab",
        "session": "main",
        "tab": 1,
    }
    assert payload["focus_requested"] is False
    assert payload["focus_verified"] is True
    assert payload["degraded"] is False
    assert server.zellij.created_tabs == [{
        "session": "main",
        "tab_id": 1,
        "name": None,
        "cwd": None,
        "command": ["bash"],
    }]
    assert server.zellij.focused_tabs == [("main", 0)]


@pytest.mark.parametrize("mode,extra", [
    ("new-tab", {}),
    ("new-pane", {"tab_id": 0}),
])
def test_workspace_create_rejects_unknown_return_tab_before_creation(server, mode, extra):
    arguments = {
        "request_id": "invalid-return-{}".format(mode),
        "command": ["bash"],
        "workspace_type": mode,
        "session_name": "main",
        "return_tab_id": 99,
    }
    arguments.update(extra)

    response = error_of(server, "workspace_create", arguments)

    assert response["code"] == ErrorCode.WORKSPACE_NOT_FOUND.value
    assert server.zellij.created_tabs == []
    assert server.zellij.created_panes == []


@pytest.mark.parametrize(
    "extra",
    [{"tab_id": 0}, {"tab_id": 0, "return_tab_id": 0}, {"focus": True}],
)
def test_workspace_create_rejects_tab_options_for_new_session(server, extra):
    response = error_of(server, "workspace_create", dict({
        "request_id": "invalid-new-session-{}".format(sorted(extra)),
        "command": ["bash"],
        "workspace_type": "new-session",
        "session_name": "build",
    }, **extra))

    assert response["code"] == ErrorCode.INVALID_ARGUMENT.value
    assert server.zellij.created_sessions == []


def test_workspace_create_rejects_an_existing_new_session_name(server):
    response = error_of(server, "workspace_create", {
        "request_id": "duplicate-session",
        "command": ["bash"],
        "workspace_type": "new-session",
        "session_name": "main",
    })

    assert response["code"] == ErrorCode.INVALID_ARGUMENT.value
    assert server.zellij.created_sessions == []

    server.zellij.session_panes.pop("main")
    server.zellij.session_tabs.pop("main")
    repeated = result_of(server, "workspace_create", {
        "request_id": "duplicate-session",
        "command": ["bash"],
        "workspace_type": "new-session",
        "session_name": "main",
    })
    assert repeated["session"] == "main"


def test_workspace_create_confirms_requested_tab_membership(server):
    server.zellij.session_tabs["main"].append(tab(7, name="Build"))
    create_pane = server.zellij.create_pane

    def create_in_wrong_tab(**kwargs):
        workspace = create_pane(**kwargs)
        created = server.zellij.session_panes["main"][-1]
        created["tab_id"] = 0
        return workspace

    server.zellij.create_pane = create_in_wrong_tab
    response = error_of(server, "workspace_create", {
        "request_id": "wrong-tab",
        "command": ["bash"],
        "workspace_type": "new-pane",
        "session_name": "main",
        "tab_id": 7,
    })

    assert response["code"] == ErrorCode.INTERNAL_ERROR.value
    assert response["details"]["actual_tab_id"] == 0
    repeated = error_of(server, "workspace_create", {
        "request_id": "wrong-tab",
        "command": ["bash"],
        "workspace_type": "new-pane",
        "session_name": "main",
        "tab_id": 7,
    })
    assert repeated["code"] == ErrorCode.INVALID_ARGUMENT.value
    assert len(server.zellij.created_panes) == 1


def test_workspace_create_request_id_returns_cached_result_and_rejects_conflict(server):
    arguments = {
        "request_id": "same-create",
        "command": ["bash"],
        "workspace_type": "new-pane",
        "session_name": "main",
    }
    first = result_of(server, "workspace_create", arguments)
    repeated = result_of(server, "workspace_create", dict(arguments))
    conflict = error_of(server, "workspace_create", dict(arguments, command=["sh"]))

    assert repeated == first
    assert conflict["code"] == ErrorCode.INVALID_ARGUMENT.value
    assert len(server.zellij.created_panes) == 1


def test_request_cache_capacity_rejects_new_ids_without_evicting_old_results(server):
    server.MAX_REQUEST_CACHE_ENTRIES = 1
    first_arguments = {
        "request_id": "first-create",
        "command": ["bash"],
        "workspace_type": "new-pane",
        "session_name": "main",
    }
    first = result_of(server, "workspace_create", first_arguments)
    rejected = error_of(server, "workspace_create", {
        "request_id": "second-create",
        "command": ["bash"],
        "workspace_type": "new-pane",
        "session_name": "main",
    })
    repeated = result_of(server, "workspace_create", first_arguments)

    assert rejected["code"] == ErrorCode.INTERNAL_ERROR.value
    assert repeated == first
    assert len(server.zellij.created_panes) == 1


def test_tab_list_groups_live_panes_by_stable_id(server):
    server.zellij.session_tabs["main"].append(tab(7, name="Build"))
    server.zellij.session_panes["main"].append(pane("terminal_7", tab_id=7))

    payload = result_of(server, "tab_list", {
        "session_name": "main",
        "include_panes": True,
    })

    assert payload["tab_count"] == 2
    build = payload["sessions"][0]["tabs"][1]
    assert build["tab_id"] == 7
    assert build["terminal_pane_count"] == 1
    assert build["panes"][0]["pane_id"] == "terminal_7"


def test_workspace_create_new_tab_focus_and_rename_use_stable_ids(server):
    created = result_of(server, "workspace_create", {
        "request_id": "new-tab",
        "session_name": "main",
        "tab_name": "Logs",
        "command": ["tail", "-f", "/dev/null"],
        "workspace_type": "new-tab",
        "focus": False,
    })
    tab_id = created["tab_id"]
    focused = result_of(server, "tab_focus", {
        "session_name": "main",
        "tab_id": tab_id,
    })
    renamed = result_of(server, "tab_rename", {
        "session_name": "main",
        "tab_id": tab_id,
        "tab_name": "Runtime Logs",
    })

    assert created["focus_requested"] is False
    assert server.zellij.created_tabs[0]["command"] == ["tail", "-f", "/dev/null"]
    assert focused["tab_id"] == tab_id
    assert renamed["tab"]["name"] == "Runtime Logs"


def test_workspace_create_new_pane_returns_the_shared_workspace_ref_schema(server):
    payload = result_of(server, "workspace_create", {
        "request_id": "new-pane-ref",
        "session_name": "main",
        "command": ["bash"],
        "workspace_type": "new-pane",
    })

    assert payload["workspace_ref"] == {
        "type": "pane",
        "session": "main",
        "pane": payload["pane_id"],
    }


def test_tab_close_requires_force_and_refuses_the_current_mcp_tab(server):
    denied_force = error_of(server, "tab_close", {
        "session_name": "main",
        "tab_id": 0,
    })
    denied_current = error_of(server, "tab_close", {
        "session_name": "main",
        "tab_id": 0,
        "force": True,
    })

    assert denied_force["code"] == ErrorCode.PERMISSION_DENIED.value
    assert denied_current["code"] == ErrorCode.PERMISSION_DENIED.value
    assert server.zellij.closed_tabs == []


def test_tab_close_closes_a_non_current_tab(server):
    server.zellij.session_tabs["main"].append(tab(7, name="Build"))
    server.zellij.session_panes["main"].append(pane("terminal_7", tab_id=7))

    payload = result_of(server, "tab_close", {
        "session_name": "main",
        "tab_id": 7,
        "force": True,
    })

    assert payload["closed"] is True
    assert payload["verified"] is True
    assert server.zellij.closed_tabs == [("main", 7)]


def test_tab_close_rejects_unknown_session_postcondition(server):
    server.zellij.session_tabs["main"].append(tab(7, name="Build"))
    server.zellij.session_panes["main"].append(pane("terminal_7", tab_id=7))
    close_tab = server.zellij.close_tab

    def close_then_break_discovery(session, tab_id):
        closed = close_tab(session, tab_id)
        server.zellij.sessions_available = False
        return closed

    server.zellij.close_tab = close_then_break_discovery
    response = error_of(server, "tab_close", {
        "session_name": "main",
        "tab_id": 7,
        "force": True,
    })

    assert response["code"] == ErrorCode.INTERNAL_ERROR.value
    assert server.zellij.closed_tabs == [("main", 7)]


@pytest.mark.parametrize(
    "current_session,current_pane",
    [(None, "terminal_0"), ("main", None)],
)
def test_destructive_tools_fail_closed_with_incomplete_current_identity(
    server,
    current_session,
    current_pane,
):
    server.zellij.current_session = current_session
    server.zellij.current_pane = current_pane

    pane_response = error_of(server, "pane_close", {
        "session_name": "main",
        "pane_id": "terminal_1",
        "force": True,
    })
    tab_response = error_of(server, "tab_close", {
        "session_name": "main",
        "tab_id": 0,
        "force": True,
    })

    assert pane_response["code"] == ErrorCode.PERMISSION_DENIED.value
    assert tab_response["code"] == ErrorCode.PERMISSION_DENIED.value
    assert server.zellij.closed_panes == []
    assert server.zellij.closed_tabs == []


def test_tab_close_fails_closed_when_current_pane_is_stale(server):
    server.zellij.session_tabs["main"].append(tab(7, name="Build"))
    server.zellij.session_panes["main"].append(pane("terminal_7", tab_id=7))
    server.zellij.current_pane = "terminal_99"

    response = error_of(server, "tab_close", {
        "session_name": "main",
        "tab_id": 7,
        "force": True,
    })

    assert response["code"] == ErrorCode.PERMISSION_DENIED.value
    assert server.zellij.closed_tabs == []


def test_destructive_tools_fail_closed_when_current_session_is_stale(server):
    server.zellij.current_session = "missing"

    response = error_of(server, "pane_close", {
        "session_name": "main",
        "pane_id": "terminal_1",
        "force": True,
    })

    assert response["code"] == ErrorCode.PERMISSION_DENIED.value
    assert server.zellij.closed_panes == []


def test_live_terminal_pane_resolver_requires_explicit_session(server):
    explicit = result_of(server, "pane_screen", {
        "session_name": "main",
        "pane_id": "terminal_1",
    })
    inferred = error_of(server, "pane_screen", {"pane_id": "terminal_1"})

    assert explicit["session"] == "main"
    assert inferred["code"] == ErrorCode.INVALID_ARGUMENT.value
    assert explicit["pane_id"] == "terminal_1"


def test_live_terminal_pane_resolver_fails_closed_on_unknown_discovery(server):
    server.zellij.panes_available = False
    response = error_of(server, "pane_screen", {
        "session_name": "main",
        "pane_id": "terminal_1",
    })

    assert response["code"] == ErrorCode.INTERNAL_ERROR.value
    assert server.zellij.captures == []


def test_live_terminal_pane_resolver_rejects_plugin_and_unknown_panes(server):
    plugin = error_of(server, "pane_write_text", {
        "session_name": "main",
        "pane_id": "plugin_0",
        "text": "blocked",
    })
    missing = error_of(server, "pane_write_text", {
        "session_name": "main",
        "pane_id": "terminal_99",
        "text": "blocked",
    })

    assert plugin["code"] == ErrorCode.PERMISSION_DENIED.value
    assert missing["code"] == ErrorCode.WORKSPACE_NOT_FOUND.value
    assert server.zellij.writes == []


def test_pane_write_sends_literal_text_to_the_resolved_terminal(server):
    payload = result_of(server, "pane_write_text", {
        "session_name": "main",
        "pane_id": "terminal_1",
        "text": "printf '%s' hello",
    })

    assert payload["session"] == "main"
    assert payload["pane_id"] == "terminal_1"
    assert server.zellij.writes == [{
        "session": "main",
        "pane_id": "terminal_1",
        "text": "printf '%s' hello",
        "enter": False,
    }]


@pytest.mark.parametrize("key", ["Enter", "Ctrl-C", "F12", "Escape"])
def test_pane_write_sends_only_schema_whitelisted_keys(server, key):
    result_of(server, "pane_send_key", {
        "session_name": "main",
        "pane_id": "terminal_1",
        "key": key,
    })
    assert server.zellij.keys[-1] == {
        "session": "main",
        "pane_id": "terminal_1",
        "keys": key,
    }


def test_split_pane_input_tools_reject_cross_kind_fields(server):
    text_response = error_of(server, "pane_write_text", {
        "session_name": "main",
        "pane_id": "terminal_1",
        "text": "status",
        "key": "Enter",
    })
    key_response = error_of(server, "pane_send_key", {
        "session_name": "main",
        "pane_id": "terminal_1",
        "key": "Enter",
        "text": "status",
    })

    assert text_response["code"] == ErrorCode.INVALID_ARGUMENT.value
    assert key_response["code"] == ErrorCode.INVALID_ARGUMENT.value
    assert server.zellij.writes == []
    assert server.zellij.keys == []



def test_pane_screen_strips_ansi_by_default(server):
    server.zellij.screens[("main", "terminal_1")] = "\x1b[32mready\x1b[0m\n"
    payload = result_of(server, "pane_screen", {
        "session_name": "main",
        "pane_id": "terminal_1",
    })

    assert payload["text"] == "ready\n"
    assert payload["full"] is False
    assert payload["ansi"] is False


def test_pane_screen_forwards_full_and_preserves_requested_ansi(server):
    server.zellij.screens[("main", "terminal_1")] = "\x1b[32mready\x1b[0m\n"
    payload = result_of(server, "pane_screen", {
        "session_name": "main",
        "pane_id": "terminal_1",
        "full": True,
        "ansi": True,
    })

    assert payload["text"] == "\x1b[32mready\x1b[0m\n"
    assert payload["full"] is True
    assert payload["ansi"] is True
    assert payload["truncated"] is False
    assert server.zellij.captures == [{
        "session": "main",
        "pane_id": "terminal_1",
        "full": True,
        "ansi": True,
    }]


def test_pane_screen_reports_bounded_truncation(server):
    limit = getattr(server, "MAX_PANE_SCREEN_CHARS", 262144)
    server.zellij.screens[("main", "terminal_1")] = "x" * (limit + 17)

    payload = result_of(server, "pane_screen", {
        "session_name": "main",
        "pane_id": "terminal_1",
        "full": True,
    })

    assert payload["truncated"] is True
    assert len(payload["text"]) <= limit


def test_rpc_pane_screen_stays_within_response_bytes_for_unicode(server):
    limit = server.MAX_PANE_SCREEN_CHARS
    server.zellij.screens[("main", "terminal_1")] = "界" * limit

    response = run_async(server.handle_rpc_message({
        "jsonrpc": "2.0",
        "id": 19,
        "method": "tools/call",
        "params": {
            "name": "pane_screen",
            "arguments": {
                "session_name": "main",
                "pane_id": "terminal_1",
                "full": True,
            },
        },
    }))

    serialized = server._json_dumps(response).encode("utf-8")
    payload = response["result"]["structuredContent"]
    assert len(serialized) <= server.MAX_RPC_RESPONSE_BYTES
    assert payload["truncated"] is True
    assert 0 < len(payload["text"]) < limit


def test_pane_close_requires_force(server):
    response = error_of(server, "pane_close", {
        "session_name": "main",
        "pane_id": "terminal_1",
    })

    assert response["code"] == ErrorCode.PERMISSION_DENIED.value
    assert server.zellij.closed_panes == []


def test_pane_close_refuses_plugin_current_and_unknown_targets(server):
    plugin = error_of(server, "pane_close", {
        "session_name": "main",
        "pane_id": "plugin_0",
        "force": True,
    })
    current = error_of(server, "pane_close", {
        "session_name": "main",
        "pane_id": "terminal_0",
        "force": True,
    })
    unknown = error_of(server, "pane_close", {
        "session_name": "main",
        "pane_id": "terminal_99",
        "force": True,
    })

    assert plugin["code"] == ErrorCode.PERMISSION_DENIED.value
    assert current["code"] == ErrorCode.PERMISSION_DENIED.value
    assert unknown["code"] == ErrorCode.WORKSPACE_NOT_FOUND.value
    assert server.zellij.closed_panes == []


def test_pane_close_fails_closed_when_discovery_is_unknown(server):
    server.zellij.panes_available = False
    response = error_of(server, "pane_close", {
        "session_name": "main",
        "pane_id": "terminal_1",
        "force": True,
    })

    assert response["code"] == ErrorCode.INTERNAL_ERROR.value
    assert server.zellij.closed_panes == []


def test_pane_close_reports_unknown_postcondition_after_action(server):
    server.zellij.close_breaks_session_discovery = True
    response = error_of(server, "pane_close", {
        "session_name": "main",
        "pane_id": "terminal_1",
        "force": True,
    })

    assert response["code"] == ErrorCode.INTERNAL_ERROR.value
    assert server.zellij.closed_panes == [("main", "terminal_1")]


def test_pane_close_closes_only_the_resolved_terminal(server):
    payload = result_of(server, "pane_close", {
        "session_name": "main",
        "pane_id": "terminal_1",
        "force": True,
    })

    assert payload["closed"] is True
    assert payload["verified"] is True
    assert server.zellij.closed_panes == [("main", "terminal_1")]
    assert server.zellij.closed_sessions == []
    remaining = {
        item["pane_id"] for item in server.zellij.session_panes["main"]
    }
    assert remaining == {"terminal_0", "plugin_0"}


def test_pane_close_does_not_delete_a_plugin_only_session(server):
    server.zellij = FakeZellijDriver(inside=False)
    server.zellij.add_session("other")
    server.zellij.session_panes["other"] = [
        pane("terminal_1"),
        pane("plugin_0", plugin=True),
    ]

    payload = result_of(server, "pane_close", {
        "session_name": "other",
        "pane_id": "terminal_1",
        "force": True,
    })

    assert payload["session_closed"] is False
    assert server.zellij.closed_sessions == []
    assert [item["pane_id"] for item in server.zellij.session_panes["other"]] == [
        "plugin_0"
    ]
