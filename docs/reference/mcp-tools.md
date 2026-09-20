# MCP Tools Reference

[中文](mcp-tools.cn.md) | [English](mcp-tools.md)

This is the detailed interface reference for the root [SPEC](../../SPEC.md). The sole runtime schema source is [`zellij_mcp/server/tool_catalog.py`](../../zellij_mcp/server/tool_catalog.py). There are exactly 11 public tools; this reference, SPEC, and actual tools/list output must agree.

## Common conventions

- Tool arguments must be an object.
- Undeclared fields are rejected.
- Identifiers are limited to 256 characters.
- `cwd` is limited to 4096 characters.
- Command is limited to 256 items and 512 KiB of total UTF-8 data.
- Environment is limited to 256 entries and 65536 total UTF-8 bytes.
- `pane_write_text.text` is limited to both 65536 characters and 65536 UTF-8 bytes.
- Pane resources are identified by `session_name + pane_id`.
- Exact pane and Tab operations require explicit `session_name`; only list tools and creation target resolution can use a default session.
- Call a list tool before modifying an existing pane or Tab.
- `workspace_type=new-session` requires the target session not to exist.
- `workspace_type` defaults to `auto`: choose `new-tab` inside zellij or when `session_name` is supplied; otherwise choose a background `new-session`.
- `workspace_type=new-pane` creates a pane in the target session.
- Close operations are rejected when the server is inside zellij but cannot confirm the current MCP pane identity.

## Caller operation guidance

1. **Discover before acting**: use `session_name + pane_id/tab_id` from list results. A pane ID looks like `terminal_3`; `tab_id` is a stable ID, not a display position. Do not guess IDs. Check `degraded/failed_sessions` when discovery is incomplete.
2. **Preserve focus by default**: do not call `tab_focus` unless requested by the user or their attention is needed; keep creation at `focus=false`. Discovery, screen reading, and input need no Tab switch. Explain necessary focus changes and do not repeatedly restore stale focus over concurrent user choices.
3. **Clean up promptly after verified completion**: when a task's pane/Tab has exited or completed and retention was not requested, collect necessary output, refresh discovery, and close it promptly. Prefer `pane_close`; use `tab_close` only after confirming all work in that Tab can be cleaned up. Preserve unrelated, running, or retained work. Verify or ask when ownership or completion is unclear.
4. **A quiet screen is not completion evidence**: `accepted=true` means only that input was accepted. A screen snapshot or brief lack of output does not prove command exit. Use program completion signals with task context and inspect `verified/session_closed` after closing.

`initialize.instructions` contains only selection criteria and minimal shared constraints: use Zellij when requested, or for persistent interactive terminals, background terminal tasks, or terminal access on a configured remote server; otherwise prefer the Host's normal execution tools. Relevant tool descriptions retain operational and safety guidance; `workspace_create` also identifies persistent interactive and background terminal tasks. All top-level parameters have `description`; booleans and `workspace_type` include schema `default`. Defaults describe existing runtime behavior; schemas do not automatically fill arguments. Whether guidance, annotations, and parameter descriptions reach the model depends on the Host; `tools/list` still returns all 11 tools, not progressive loading. No `outputSchema`, resources, or prompts are currently provided; result fields remain documented here and in tool descriptions.

These rules do not imply automatic server-side completion detection or resource closure. Closing still requires explicit `force=true` and identity safeguards. Closing the active Tab or last pane may cause zellij itself to change visible focus or end the session.

Descriptions prioritize purpose, safety and parameter interactions rather than repeating schema types, limits or defaults. Detailed contracts remain below; shortening descriptions does not change runtime behavior or load tools on demand.

## 1. zellij_mcp_doctor

Check Python, zellij, direct pane I/O, and the server's zellij context. It does not independently validate Host configuration or authorization policies; `capabilities.host` is `not_checked`.

Arguments: an empty object.

Main result fields: `ok`, `zellij-mcp`, `python`, `zellij`, `capabilities`, `warnings`, `fixes`.

## 2. workspace_create

Create a pane, Tab, or session and run an argv command directly.

Required parameters:

- `request_id`: nonempty creation retry key. Reuse the same ID with identical arguments. The cache belongs only to the current stdio process or HTTP MCP session and does not survive restart. Discover actual resources when the outcome is unknown; do not blindly retry with a new ID.
- `command`: nonempty argv array, not a shell string. Pipes, redirects, and expansion require an explicit shell.

Optional parameters:

- `cwd`: working directory, preferably absolute. Omission uses runtime/zellij context, not necessarily the Host's project directory.
- `environment`: string map adding or overriding variables for this command only; omission adds none.
- `workspace_type`: defaults to `auto`; other values are `new-pane`, `new-tab`, and `new-session`.
- `session_name`: existing target for `new-pane/new-tab`, defaulting to the current or sole active session; new name for `new-session`, generated when omitted. Supplying it to `auto` selects `new-tab`.
- `tab_name`: optional name for `new-tab`.
- `tab_id`: stable target Tab ID for `new-pane`; also requires `session_name`.
- `return_tab_id`: Tab ID in the same session to restore with `focus=false`. `new-tab` can use it alone; `new-pane` also requires target `tab_id`.
- `focus`: defaults to false. True requests focus on a new Tab or explicitly targeted `new-pane tab_id` and cannot accompany `return_tab_id`. Use true only when requested by the user or their attention is needed.

Main result fields: `workspace_ref`, `session`, `tab_id`, `pane_id`, `attach_hint`, `direct`, focus verification fields, and `degraded`.

`workspace_ref` always contains `type` and `session`. Type is `session`, `pane`, or `tab`; session and pane references contain `pane`, and Tab references contain `tab`.

Supplying `tab_id` also requires `session_name`.

`return_tab_id` must exist in the target session before creation. Otherwise, return `workspace_not_found` without creating a Tab or pane.

`new-tab` returns `tab_id` rather than `pane_id`; discover the target pane afterward with `tab_list`. New Tabs are created with no-focus. New-pane in a specified Tab attempts to preserve focus; callers still inspect focus verification and degraded fields. Usually omit `return_tab_id` to avoid explicit restoration overriding a concurrent user switch.

## 3. workspace_list

List live sessions and panes.

Parameters:

- `session_name`: specified session, taking precedence over `all_sessions`; if neither is selected, use the current or sole active session.
- `all_sessions`: defaults to false; read all active sessions.
- `include_plugins`: defaults to false; include plugin panes in details without affecting the plugin counts always reported.

Main result fields: `current_session`, `current_pane`, `session_count`, `total_pane_count`, `pane_count`, `terminal_pane_count`, `plugin_pane_count`, `sessions`, `degraded`, `failed_sessions`.

## 4. tab_list

List stable Tab IDs and pane membership.

Parameters:

- `session_name`: specified session; when omitted with `all_sessions=false`, use the current or sole active session.
- `all_sessions`: defaults to false; read all active sessions. Cannot accompany `session_name`.
- `include_panes`: defaults to true; include terminal/plugin panes in Tab details.

Main result fields: `current_session`, `current_pane`, `session_count`, `tab_count`, `sessions`.

Each Tab includes `tab_id`, position, name, active-state source, and pane counts.

## 5. tab_focus

Focus a Tab by stable ID.

This changes user-visible focus. Use it only at the user's request or when their attention is needed, and explain why. Do not switch focus for list, screen, or pane input.

Required parameters: `session_name`, `tab_id`.

Main result fields: `focused`, `changed`, `session`, `tab_id`, `previous_tab_id`, `focus_verified`, `verified`, `degraded`.

## 6. tab_rename

Rename a Tab by stable ID.

Required parameters: `session_name`, `tab_id`, `tab_name`.

Main result fields: `renamed`, `changed`, `session`, `tab_id`, `previous_name`, `tab`, `verified`, `degraded`.

## 7. tab_close

Close a Tab by stable ID.

Required parameters: `session_name`, `tab_id`.

Optional parameter: `force`. It must be true to execute closing.

Main result fields: `closed`, `session`, `tab_id`, `tab`, `pane_ids`, `resources`, `verified`, `session_closed`.

The Tab containing the current MCP pane is protected. Clean up promptly after completion when retention is unnecessary, but first save results and inspect every pane through `tab_list(include_panes=true)`. If only one pane is done, prefer closing it to avoid terminating other work.

## 8. pane_write_text

Write literal text to a live terminal pane. This single-purpose schema prevents Hosts from incorrectly converting mutually exclusive optional fields into jointly required fields.

Required parameters: `session_name`, `pane_id`, `text`.

`text` invokes `write-chars` without appending Enter; embedded newlines may still submit input. Confirm the foreground program first. Success only means input was accepted, with `completion_verified=false`.

Main result fields: `written`, `accepted`, `session`, `pane_id`, `kind="text"`, `bytes`, `completion_verified`.

## 9. pane_send_key

Send one restricted key to a live terminal pane.

Enter may submit a command; Ctrl-C/Ctrl-D may interrupt or exit the foreground program. No Tab switch is needed. Confirm the target first; accepted input does not mean command completion.

Required parameters: `session_name`, `pane_id`, `key`.

Key enum:

```text
Enter Tab Backspace Delete Up Down Right Left Home End PageUp PageDown
F1 F2 F3 F4 F5 F6 F7 F8 F9 F10 F11 F12 Ctrl-C Ctrl-D Escape
```

Public names `Ctrl-C`, `Ctrl-D`, and `Escape` map respectively to the single zellij key specifications `Ctrl c`, `Ctrl d`, and `Esc`.

Main result fields: `written`, `accepted`, `session`, `pane_id`, `kind="key"`, `bytes=0`, `completion_verified`.

## 10. pane_screen

Read the screen of a live terminal pane.

Required parameters: `session_name`, `pane_id`.

Optional parameters:

- `full`: defaults to false for the viewport; true reads full scrollback, still subject to truncation.
- `ansi`: defaults to false to remove ANSI; true preserves ANSI.

Main result fields: `session`, `pane_id`, `text`, `full`, `ansi`, `truncated`, `source`. Text is first limited to 262144 characters. stdio tools/call additionally retains only the tail as needed to meet the response byte limit.

No screen output does not prove process exit or task completion; it is insufficient grounds to close resources.

## 11. pane_close

Close a live terminal pane.

Required parameters: `session_name`, `pane_id`.

Optional parameter: `force`. It must be true to execute closing.

Main result fields: `closed`, `verified`, `session`, `pane_id`, `session_closed`, `resources`.

Plugin panes and the current MCP pane are protected.

When task resources are confirmed exited or complete and the user has not requested retention, save results, refresh discovery, and close promptly. Preserve unrelated, running, or retained work; do not guess when state is unclear.

`pane_close` closes only the specified pane and does not proactively delete a session containing only plugin panes. If zellij ends the session itself after the pane disappears, return `session_closed=true`.

## Error semantics

| Code | Meaning |
|------|---------|
| `invalid_argument` | Argument type, required fields, enum, range, mutual exclusion, or size violates the schema |
| `zellij_not_available` | zellij is unavailable |
| `workspace_not_found` | The session, Tab, or pane does not exist |
| `permission_denied` | Missing force or protected target |
| `internal_error` | Failed zellij action, resource discovery, or postcondition verification |
