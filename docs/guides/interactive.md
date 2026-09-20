# Direct Pane Operations Guide

[中文](interactive.cn.md) | [English](interactive.md)

## Connection check

After connecting the Host, first call:

```text
zellij_mcp_doctor
```

Confirm that `capabilities.zellij`, `zellij_stable_tab_control`, and `zellij_direct_pane_io` meet the operation's requirements.

## Discover resources

Inspect the current session:

```json
{
  "session_name": "dev",
  "all_sessions": false,
  "include_plugins": true
}
```

After calling `workspace_list`, retain the target `session` and `pane_id`. Call `tab_list` when Tab information is needed.

## Create a pane

Create a shell in a specified session:

```json
{
  "request_id": "shell-001",
  "command": ["/bin/sh"],
  "workspace_type": "new-pane",
  "session_name": "dev"
}
```

Create a separate session:

```json
{
  "request_id": "session-001",
  "command": ["/bin/sh"],
  "workspace_type": "new-session",
  "session_name": "zellij-mcp-demo"
}
```

The creation result returns `session`, `pane_id`, `tab_id`, and `attach_hint`.

## Write to a pane

Write text:

```json
{
  "session_name": "zellij-mcp-demo",
  "pane_id": "terminal_0",
  "text": "printf 'hello\\n'"
}
```

Send Enter:

```json
{
  "session_name": "zellij-mcp-demo",
  "pane_id": "terminal_0",
  "key": "Enter"
}
```

Use `pane_write_text` for text and `pane_send_key` for keys.

## Read a pane

Read the viewport:

```json
{
  "session_name": "zellij-mcp-demo",
  "pane_id": "terminal_0",
  "full": false,
  "ansi": false
}
```

Read full scrollback while preserving ANSI:

```json
{
  "session_name": "zellij-mcp-demo",
  "pane_id": "terminal_0",
  "full": true,
  "ansi": true
}
```

Check the returned `truncated` field. When text exceeds 262144 characters, the result retains the tail.

## Tab operations

1. Call `tab_list` to obtain a stable `tab_id`.
2. Call `workspace_create(workspace_type="new-tab")` to create a Tab.
3. Call `workspace_create` with `workspace_type="new-pane"`, `session_name`, and `tab_id` to create a pane directly in the target Tab.
4. Call `tab_focus` or `tab_rename` to change the target Tab.
5. Call `tab_close(force=true)` to close the target Tab.

## Safe closing

Close a pane:

```json
{
  "session_name": "zellij-mcp-demo",
  "pane_id": "terminal_0",
  "force": true
}
```

Call `workspace_list` or `tab_list` again before closing. Plugin panes, the current MCP pane, and Tabs containing the current MCP pane are rejected.
