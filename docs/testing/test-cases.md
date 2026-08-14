# Direct Pane Test Cases

[中文](test-cases.cn.md) | [English](test-cases.md)

## zellij_mcp_doctor

### Available environment

- Input: an empty object.
- Preconditions: Python and zellij are available.
- Expected: versions, background creation, stable Tabs, direct pane I/O, current context, and warnings.

### Missing zellij

- Input: an empty object.
- Preconditions: no zellij on PATH.
- Expected: `ok=false`, false capability, and installation guidance.

## workspace_create

### Create a pane

- Input: `request_id`, `command=["/bin/sh"]`, `workspace_type="new-pane"`, and target session.
- Expected: actual `session`, `pane_id`, `tab_id`, and attach hint.

### Create a session

- Input: `workspace_type="new-session"` and unique `session_name`.
- Expected: a background session whose initial terminal pane runs the specified command.

### argv and environment

- Input: argv containing spaces, quotes, and Unicode, plus a structured environment map.
- Expected: arguments passed individually; cwd and environment values observable inside the pane.

### Specify a Tab

- Input: target `tab_id`.
- Expected: the new pane's `tab_id` matches the target.

### Create a Tab and restore focus

- Input: `workspace_type="new-tab"`, target session, `focus=false`, and an existing `return_tab_id`.
- Expected: the new Tab's initial pane runs command and the target session's active Tab is restored to `return_tab_id`.

### Invalid focus restoration target

- Input: `new-tab` or a Tab-targeted `new-pane`, with nonexistent `return_tab_id`.
- Expected: `workspace_not_found` before creation, without invoking a zellij creation action.

### Invalid input

- Input: empty command, oversized fields, invalid environment, or unknown fields.
- Expected: `invalid_argument`, without zellij actions.

## workspace_list

### Current session

- Preconditions: 3 terminal panes and 1 plugin pane.
- Expected: `total_pane_count=4`, `pane_count=3`, `terminal_pane_count=3`, `plugin_pane_count=1`.

### All sessions

- Input: `all_sessions=true`.
- Expected: active session aggregates and pane details for each session.

### Discovery failure

- Preconditions: zellij session or pane enumeration command fails.
- Expected: structured error instead of false zero counts.

## tab_list

### Multiple Tabs

- Input: target session and `include_panes=true`.
- Expected: stable `tab_id`, name, active-state source, four pane counts, and pane membership.

### Unconfirmed pane membership

- Preconditions: a pane's Tab ID cannot be mapped.
- Expected: `internal_error`.

## workspace_create new-tab

### Create a shell Tab

- Input: unique `request_id`, `command=["/bin/sh"]`, `workspace_type="new-tab"`, and `tab_name`.
- Expected: new `tab_id` and Tab information.

### Create a command Tab

- Input: command, cwd, and environment.
- Expected: the initial pane runs command directly.

### Focus parameters

- Input: `focus=true` or `return_tab_id`.
- Expected: action acceptance and observable focus verification results.

## tab_focus

- Input: stable `tab_id`.
- Expected: successful target Tab action; `verified=true` when active state is observable.

## tab_rename

- Input: stable `tab_id` and a new name.
- Expected: rename by ID and re-enumerate to verify the name.

## tab_close

### Missing force

- Input: target `tab_id`.
- Expected: `permission_denied`.

### Tab containing the current MCP pane

- Input: target `tab_id` and `force=true`.
- Expected: `permission_denied`; the Tab remains.

### Normal close

- Input: another Tab and `force=true`.
- Expected: re-enumerate to confirm Tab or session state and return `verified=true`.

## pane_write_text

- Input: `session_name`, `pane_id`, and `text`.
- Expected: invoke `write-chars`, returning `kind="text"` and UTF-8 byte count.

### Crossed fields

- Input: an additional `key` field.
- Expected: `invalid_argument`, without invoking a zellij action.

## pane_send_key

- Input: `key="Enter"`.
- Expected: invoke `send-keys`, returning `kind="key"`.

### Crossed fields

- Input: an additional `text` field.
- Expected: `invalid_argument`, without invoking a zellij action.

## pane_screen

### Viewport

- Input: `full=false`, `ansi=false`.
- Expected: viewport text with ANSI escapes removed.

### Full and ANSI

- Input: `full=true`, `ansi=true`.
- Expected: full dump-screen with ANSI preserved.

### Truncation

- Preconditions: screen exceeds 262144 characters.
- Expected: retain the last 262144 characters and set `truncated=true`.

## pane_close

### Missing force

- Expected: `permission_denied`.

### Plugin pane and current MCP pane

- Input: `force=true`.
- Expected: `permission_denied`; the target remains.

### Normal close

- Input: another terminal pane and `force=true`.
- Expected: rediscover resources and return `closed=true`, `verified=true`.

### Unknown postcondition

- Preconditions: session or panes cannot be enumerated after closing.
- Expected: `internal_error`.
