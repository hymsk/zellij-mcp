# ADR 0003: Direct Pane Runtime

[中文](0003-direct-pane-runtime.cn.md) | [English](0003-direct-pane-runtime.md)

## Status

Accepted.

## Decision

- zellij sessions, Tabs, and terminal panes are the runtime resources.
- Address terminal panes with `session_name + pane_id`.
- `workspace_create` runs an argv `command` directly in a pane, Tab, or session.
- `workspace_list` and `tab_list` read live zellij resources.
- `pane_write_text` uses `write-chars`; `pane_send_key` uses an enumerated `send-keys` interface.
- `pane_screen` uses `dump-screen` with viewport, full scrollback, and ANSI options.
- Screen text is limited to 262144 characters.
- `pane_close` and `tab_close` require `force=true` and protect special resources, including the current MCP pane.
- Exact pane and Tab operations require `session_name`. Listing can use the current or sole session.
- `pane_close` does not actively delete sessions or expand pane-level authorization into session deletion.
- MCP protocol, tool runtime, zellij subprocess calls, and discovery parsing use separate modules; `ZellijMCPServer` remains the public facade.
- Wheels embed the full source commit and tracked-file dirty state, available through version and doctor JSON.

## Resource invariants

- Resolve session names against live sessions.
- Use stable `tab_id` values.
- Terminal and plugin panes have separate identifier spaces.
- Discover before mutation and confirm after closing.
- Return errors for unknown resource states.

## Tool surface

The exact public tool set is:

```text
zellij_mcp_doctor
workspace_create
workspace_list
tab_list
tab_focus
tab_rename
tab_close
pane_write_text
pane_send_key
pane_screen
pane_close
```

Every tool declares `readOnlyHint`, `destructiveHint`, `idempotentHint`, and `openWorldHint`. Hints describe behavior; they do not grant permissions or weaken checks.
