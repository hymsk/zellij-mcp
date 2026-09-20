#!/usr/bin/env python3
"""Assert the bounded stdio MCP protocol without creating zellij resources."""

import json
import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

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
ANNOTATION_FIELDS = {
    "readOnlyHint",
    "destructiveHint",
    "idempotentHint",
    "openWorldHint",
}


def server_command():
    """Use source by default or an explicitly supplied installed wrapper command."""
    if len(sys.argv) > 1:
        return sys.argv[1:]
    return [sys.executable, "-m", "zellij_mcp", "serve"]


def main():
    """Exercise initialize, notification, tools and parse-error recovery over stdio."""
    command = server_command()
    working_directory = PROJECT_ROOT if len(sys.argv) == 1 else os.getcwd()
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "zellij_mcp_doctor", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "unknown_tool", "arguments": {}},
        },
    ]
    input_text = "\n".join(json.dumps(item) for item in requests)
    input_text += "\n{invalid json\n"
    input_text += "{" + '"value":' + "[" * 1100 + "0" + "]" * 1100 + "}\n"
    input_text += json.dumps({"value": "x" * (1024 * 1024)}) + "\n"
    input_text += json.dumps({
        "jsonrpc": "2.0",
        "id": 6,
        "method": "ping",
        "params": {},
    }) + "\n"
    completed = subprocess.run(
        command,
        cwd=working_directory,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=30,
    )
    responses = [json.loads(line) for line in completed.stdout.splitlines()]

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    assert [item.get("id") for item in responses] == [
        1,
        2,
        3,
        4,
        5,
        None,
        None,
        None,
        6,
    ]
    assert responses[0]["result"]["serverInfo"]["name"] == "zellij-mcp"
    instructions = responses[0]["result"]["instructions"]
    assert "when the user requests zellij" in instructions
    assert "persistent interactive terminal" in instructions
    assert "background terminal task" in instructions
    assert "configured remote server" in instructions
    assert "Otherwise, prefer the Host's normal execution tools" in instructions
    assert "Discover existing resources" in instructions
    assert "preserve user focus and unrelated work" in instructions
    assert len(instructions) <= 360
    listed_tools = responses[2]["result"]["tools"]
    assert tuple(item["name"] for item in listed_tools) == PUBLIC_TOOLS
    assert len({item["name"] for item in listed_tools}) == len(PUBLIC_TOOLS)
    for tool in listed_tools:
        assert set(tool["annotations"]) == ANNOTATION_FIELDS
        assert all(type(value) is bool for value in tool["annotations"].values())
        assert tool["inputSchema"]["type"] == "object"
        assert tool["inputSchema"]["additionalProperties"] is False
        for schema in tool["inputSchema"]["properties"].values():
            assert schema.get("description", "").strip()
            if schema["type"] == "boolean":
                assert type(schema.get("default")) is bool
    tools_by_name = {tool["name"]: tool for tool in listed_tools}
    create_properties = tools_by_name["workspace_create"]["inputSchema"]["properties"]
    assert create_properties["focus"]["default"] is False
    assert "persistent interactive or background terminal tasks" in (
        tools_by_name["workspace_create"]["description"]
    )
    assert "attention" in tools_by_name["tab_focus"]["description"]
    for name in ("pane_close", "tab_close"):
        assert "verified finished tasks" in tools_by_name[name]["description"]
        assert "never unrelated/running/retained work" in tools_by_name[name]["description"]
        assert "Must be true to close" in (
            tools_by_name[name]["inputSchema"]["properties"]["force"]["description"]
        )
    assert responses[3]["result"]["isError"] is False
    assert responses[4]["result"]["isError"] is True
    assert responses[5]["error"]["code"] == -32700
    assert responses[6]["error"]["code"] == -32700
    assert responses[7]["error"]["code"] == -32600
    assert responses[8]["result"] == {}
    print(json.dumps({
        "ok": True,
        "server_command": command,
        "tool_count": len(PUBLIC_TOOLS),
        "response_count": len(responses),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
