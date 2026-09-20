"""Static MCP tool catalog and bounded input schemas."""

from typing import Any, Dict

MAX_IDENTIFIER_LENGTH = 256
MAX_PATH_LENGTH = 4096
MAX_COMMAND_ITEMS = 256
MAX_COMMAND_ARGUMENT_LENGTH = 65536
MAX_COMMAND_BYTES = 512 * 1024
MAX_WRITE_TEXT_LENGTH = 64 * 1024
MAX_WRITE_TEXT_BYTES = 64 * 1024
MAX_ENVIRONMENT_ITEMS = 256
MAX_ENVIRONMENT_BYTES = 65536
MAX_TAB_ID = 2147483647
ALLOWED_KEYS = (
    "Enter",
    "Tab",
    "Backspace",
    "Delete",
    "Up",
    "Down",
    "Right",
    "Left",
    "Home",
    "End",
    "PageUp",
    "PageDown",
    "F1",
    "F2",
    "F3",
    "F4",
    "F5",
    "F6",
    "F7",
    "F8",
    "F9",
    "F10",
    "F11",
    "F12",
    "Ctrl-C",
    "Ctrl-D",
    "Escape",
)
READ_ONLY_TOOLS = {
    "zellij_mcp_doctor",
    "workspace_list",
    "tab_list",
    "pane_screen",
}
NON_DESTRUCTIVE_MUTATIONS = {"tab_focus", "tab_rename"}
OPEN_WORLD_MUTATIONS = {
    "workspace_create",
    "pane_write_text",
    "pane_send_key",
    "tab_close",
    "pane_close",
}


def build_tool_catalog() -> Dict[str, Dict[str, Any]]:
    """Build the direct-pane MCP tool catalog."""
    tools: Dict[str, Dict[str, Any]] = {
        "zellij_mcp_doctor": {
            "name": "zellij_mcp_doctor",
            "description": (
                "Diagnose setup or capability failures; inspect ok, warnings and fixes."
            ),
            "inputSchema": {"type": "object", "properties": {}},
        },
        "workspace_create": {
            "name": "workspace_create",
            "description": (
                "Run commands in zellij for persistent interactive or background terminal tasks. "
                "Keep focus=false unless the user requests a switch or needs attention. "
                "Save returned IDs; new-tab returns tab_id (use tab_list for panes). "
                "Check degraded/focus_verified. Promptly close confirmed exited or completed "
                "task resources after saving results, unless the user requested retention."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "request_id": {
                        "type": "string",
                        "description": (
                            "Retry key within this stdio process/HTTP session: "
                            "reuse with identical args; not across restarts. "
                            "After unknown outcomes, discover before retrying."
                        ),
                    },
                    "command": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                        "description": (
                            "Direct argv; shell syntax requires an explicit shell."
                        ),
                    },
                    "cwd": {
                        "type": "string",
                        "description": (
                            "Working directory; prefer absolute paths. Omitted: runtime/zellij "
                            "context, not necessarily the Host project."
                        ),
                    },
                    "environment": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": (
                            "Environment overrides for this command only."
                        ),
                    },
                    "workspace_type": {
                        "type": "string",
                        "enum": ["auto", "new-pane", "new-tab", "new-session"],
                        "default": "auto",
                        "description": (
                            "auto: new-tab inside zellij or with session_name, else new-session. "
                            "new-pane/new-tab need an existing session; "
                            "new-session runs in background, "
                            "rejecting existing names."
                        ),
                    },
                    "session_name": {
                        "type": "string",
                        "description": (
                            "Existing session for pane/tab (omitted: current or sole live); "
                            "new session name for new-session (omitted: generated)."
                        ),
                    },
                    "tab_name": {
                        "type": "string",
                        "description": (
                            "Name for new-tab only."
                        ),
                    },
                    "tab_id": {
                        "type": "integer",
                        "minimum": 0,
                        "description": (
                            "Discovered Tab ID for new-pane only; requires session_name."
                        ),
                    },
                    "return_tab_id": {
                        "type": "integer",
                        "minimum": 0,
                        "description": (
                            "Restore this same-session Tab intentionally; normally omit to avoid "
                            "overriding user focus. Requires focus=false; "
                            "new-pane also needs tab_id."
                        ),
                    },
                    "focus": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Activate the new Tab or new-pane target tab_id; "
                            "incompatible with return_tab_id."
                        ),
                    },
                },
                "required": ["request_id", "command"],
            },
        },
        "workspace_list": {
            "name": "workspace_list",
            "description": (
                "Discover live sessions and pane IDs without changing focus. "
                "pane_count=terminal_pane_count; total_pane_count also includes plugin_pane_count. "
                "Check degraded/failed_sessions."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": (
                            "Overrides all_sessions; omitted: "
                            "current or sole live unless all_sessions."
                        ),
                    },
                    "all_sessions": {
                        "type": "boolean", "default": False,
                        "description": "All live sessions when session_name is omitted.",
                    },
                    "include_plugins": {
                        "type": "boolean", "default": False,
                        "description": (
                            "Include plugin details; counts are always included. "
                            "Plugins reject I/O."
                        ),
                    },
                },
            },
        },
        "tab_list": {
            "name": "tab_list",
            "description": (
                "Discover session-local Tab IDs, active state and panes without changing focus. "
                "Use before Tab operations or after new-tab; IDs are not display positions."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": (
                            "Session to inspect; omitted: current or sole live unless all_sessions."
                        ),
                    },
                    "all_sessions": {
                        "type": "boolean", "default": False,
                        "description": (
                            "All live sessions; excludes session_name."
                        ),
                    },
                    "include_panes": {
                        "type": "boolean", "default": True,
                        "description": (
                            "Include each Tab's terminal and plugin panes."
                        ),
                    },
                },
            },
        },
        "tab_focus": {
            "name": "tab_focus",
            "description": (
                "Switch visible Tab only when the user requests it or needs attention; "
                "explain why. "
                "Never needed for discovery/read/write. Check focus_verified/degraded."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_name": {"type": "string"},
                    "tab_id": {"type": "integer", "minimum": 0},
                },
                "required": ["session_name", "tab_id"],
            },
        },
        "tab_rename": {
            "name": "tab_rename",
            "description": (
                "Rename a discovered Tab without changing focus; check verified/degraded."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_name": {"type": "string"},
                    "tab_id": {"type": "integer", "minimum": 0},
                    "tab_name": {"type": "string"},
                },
                "required": ["session_name", "tab_id", "tab_name"],
            },
        },
        "tab_close": {
            "name": "tab_close",
            "description": (
                "Close Tab and ALL panes. Save results; refresh tab_list(include_panes=true). "
                "Promptly clean up verified finished tasks, never unrelated/running/retained work. "
                "Prefer pane_close for one pane. Protects MCP Tab; may end session or change focus."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_name": {"type": "string"},
                    "tab_id": {"type": "integer", "minimum": 0},
                    "force": {"type": "boolean"},
                },
                "required": ["session_name", "tab_id"],
            },
        },
        "pane_write_text": {
            "name": "pane_write_text",
            "description": (
                "Write to the inspected pane without changing focus. No Enter appended; "
                "embedded newlines may submit. accepted means delivery, not completion."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_name": {"type": "string"},
                    "pane_id": {"type": "string"},
                    "text": {
                        "type": "string",
                        "description": (
                            "Literal text, no server-side escaping or shell interpretation."
                        ),
                    },
                },
                "required": ["session_name", "pane_id", "text"],
            },
        },
        "pane_send_key": {
            "name": "pane_send_key",
            "description": (
                "Send a key to the inspected pane without changing focus. Enter submits; "
                "Ctrl-C/Ctrl-D may interrupt/exit. Acceptance is not completion."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_name": {"type": "string"},
                    "pane_id": {"type": "string"},
                    "key": {
                        "type": "string",
                        "description": (
                            "One key, not a sequence; interpreted by the foreground program."
                        ),
                    },
                },
                "required": ["session_name", "pane_id", "key"],
            },
        },
        "pane_screen": {
            "name": "pane_screen",
            "description": (
                "Read pane output without changing focus; check truncated. "
                "At most 262144 characters, keeping the tail. A snapshot or silence alone "
                "does not prove completion."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_name": {"type": "string"},
                    "pane_id": {"type": "string"},
                    "full": {
                        "type": "boolean", "default": False,
                        "description": (
                            "Read available scrollback instead of viewport; still bounded."
                        ),
                    },
                    "ansi": {
                        "type": "boolean", "default": False,
                        "description": (
                            "Keep ANSI escapes instead of plain text."
                        ),
                    },
                },
                "required": ["session_name", "pane_id"],
            },
        },
        "pane_close": {
            "name": "pane_close",
            "description": (
                "Close a terminal pane. Save results; refresh discovery. "
                "Promptly clean up verified "
                "finished tasks, never unrelated/running/retained work; silence is not completion. "
                "Protects MCP/plugin panes. Last pane may end Tab/session; "
                "check verified/session_closed."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_name": {"type": "string"},
                    "pane_id": {"type": "string"},
                    "force": {"type": "boolean"},
                },
                "required": ["session_name", "pane_id"],
            },
        },
    }

    common_descriptions = {
        "session_name": (
            "Discovered session owning the target ID."
        ),
        "pane_id": (
            "Discovered terminal ID, e.g. terminal_3; never guess or target plugins."
        ),
        "tab_id": "Discovered Tab ID, not its display position.",
        "tab_name": "New name; ID unchanged.",
        "force": (
            "Must be true to close; confirm target/scope first. MCP protection remains."
        ),
    }
    identifier_fields = {"request_id", "session_name", "pane_id", "tab_name"}
    for name, tool in tools.items():
        read_only = name in READ_ONLY_TOOLS
        tool["annotations"] = {
            "readOnlyHint": read_only,
            "destructiveHint": not (
                read_only or name in NON_DESTRUCTIVE_MUTATIONS
            ),
            "idempotentHint": read_only or name in NON_DESTRUCTIVE_MUTATIONS,
            "openWorldHint": name in OPEN_WORLD_MUTATIONS,
        }
        schema = tool["inputSchema"]
        schema["additionalProperties"] = False
        for name, field_schema in schema.get("properties", {}).items():
            if not isinstance(field_schema, dict):
                continue
            if name in common_descriptions:
                field_schema.setdefault("description", common_descriptions[name])
            if name == "force":
                field_schema.setdefault("default", False)
            if name in identifier_fields:
                field_schema.setdefault("minLength", 1)
                field_schema.setdefault("maxLength", MAX_IDENTIFIER_LENGTH)
            elif name == "cwd":
                field_schema.setdefault("maxLength", MAX_PATH_LENGTH)
            elif name == "text":
                field_schema.setdefault("maxLength", MAX_WRITE_TEXT_LENGTH)

    for tool_name in ("workspace_create",):
        properties = tools[tool_name]["inputSchema"]["properties"]
        properties["command"]["maxItems"] = MAX_COMMAND_ITEMS
        properties["command"]["maxUtf8Bytes"] = MAX_COMMAND_BYTES
        properties["command"]["items"]["maxLength"] = MAX_COMMAND_ARGUMENT_LENGTH
        properties["environment"]["maxProperties"] = MAX_ENVIRONMENT_ITEMS
        properties["environment"]["propertyNamePattern"] = (
            r"^[A-Za-z_][A-Za-z0-9_]*$"
        )
        properties["environment"]["maxUtf8Bytes"] = MAX_ENVIRONMENT_BYTES

    for tool_name in ("workspace_create", "tab_focus", "tab_rename", "tab_close"):
        tools[tool_name]["inputSchema"]["properties"]["tab_id"]["maximum"] = MAX_TAB_ID
    for tool_name in ("workspace_create",):
        tools[tool_name]["inputSchema"]["properties"]["return_tab_id"][
            "maximum"
        ] = MAX_TAB_ID
    for tool_name in ("pane_send_key",):
        tools[tool_name]["inputSchema"]["properties"]["key"]["enum"] = list(
            ALLOWED_KEYS
        )
    for tool_name in ("pane_write_text",):
        tools[tool_name]["inputSchema"]["properties"]["text"][
            "maxUtf8Bytes"
        ] = MAX_WRITE_TEXT_BYTES
    return tools
