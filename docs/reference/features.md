# Feature Baseline

[中文](features.cn.md) | [English](features.md)

This page explains the current behavior defined by the root [SPEC](../../SPEC.md). Requirements and acceptance criteria are maintained in SPEC.

## Exact tool set

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

## Capability matrix

| Capability | Behavior |
|------------|----------|
| stdio MCP | Supports initialize, notifications, ping, tools/list, tools/call, and structured errors |
| Streamable HTTP MCP | Opt-in, loopback by default; accepts explicit IPv4/IPv6 or wildcard binding; one `/mcp` endpoint returns JSON through POST, with no SSE GET |
| HTTP security | Required Bearer token, explicit Host/Origin allowlists, bounded requests; warns for non-loopback plaintext HTTP |
| Native HTTPS | Paired PEM certificate/key, standard-library `SSLContext` with TLS 1.2 minimum; no added runtime dependencies |
| Tool annotations | All 11 tools explicitly provide read-only, destructive, idempotent, and open-world hints |
| Caller guidance | Initialize instructions and tool/parameter descriptions cover focus preservation, prompt cleanup after completion, resource targeting, and input versus completion; every top-level parameter has a description, with actual defaults for booleans and creation mode |
| Argument boundaries | Validate types, required fields, enums, lengths, UTF-8 byte counts, and unknown fields |
| Doctor | Checks Python, zellij, background creation, stable Tabs, direct pane I/O, and current context |
| Session discovery | Enumerates active sessions and distinguishes empty results from discovery failure |
| Pane discovery | Returns terminal/plugin pane details and four separate counts |
| Workspace creation | Creates a pane, Tab, or session and runs an argv command directly |
| Environment | Applies a structured map to the command |
| Tab management | Creates through `workspace_create(new-tab)`; lists, focuses, renames, and closes by stable `tab_id` |
| Creation in a specified Tab | Uses `new-pane --tab-id` and rediscovers to verify membership |
| Pane input | Separate `pane_write_text` and `pane_send_key` tools |
| Pane screen | Uses `dump-screen` for viewport or full output, optionally preserving ANSI |
| Screen limit | Returns at most 262144 characters, also subject to the stdio response byte limit; sets `truncated=true` on overflow |
| Pane close | Requires `force=true`, protects plugin panes and the current MCP pane, rejects incomplete current identity |
| Tab close | Requires `force=true`, protects the Tab containing the current MCP pane, rejects incomplete current identity |
| Installation provenance | Wheels embed the full source commit and tracked-file dirty state, queryable through version/doctor JSON |

## Resource references

Terminal pane calls use:

```json
{
  "session_name": "dev",
  "pane_id": "terminal_3"
}
```

`workspace_list` and `tab_list` are the resource discovery entry points. Callers obtain session, Tab, pane, title, command, cwd, state, and geometry information from list results.

Exact pane and Tab operations require an explicit `session_name` so session-local IDs do not resolve to the wrong resources.

## MCP annotations

- `zellij_mcp_doctor`, `workspace_list`, `tab_list`, and `pane_screen` are read-only, idempotent, closed-world tools.
- `tab_focus` and `tab_rename` are nondestructive, idempotent, closed-world mutations.
- `workspace_create`, `pane_write_text`, `pane_send_key`, `tab_close`, and `pane_close` are marked destructive/open-world and do not declare cross-process idempotency.
- `workspace_create.request_id` provides a bounded cache within one tool runtime: the current process for stdio, or current MCP session for HTTP. It does not guarantee cross-session or cross-process idempotency.

## Creation semantics

- `workspace_type=auto` selects a mode from current zellij context and the explicit session, preferring a new Tab in an existing session and otherwise creating a session.
- `workspace_type=new-pane` creates a pane in the target session.
- `workspace_type=new-tab` creates a Tab in the target session. The actual default is `auto`, selected by context.
- `workspace_type=new-session` creates a background session and rejects an explicitly named session that already exists.
- `command` is a nonempty argv array.
- `cwd` is an optional working directory.
- `environment` is an optional string map.
- `request_id` is a runtime-local idempotency key for creation. At the fixed cache limit, new creation IDs are rejected instead of evicting existing results.
- Failures known to have caused no action do not retain `request_id`; unknown action outcomes retain an unresolved state to prevent unsafe retries.

## Focus and lifecycle guidance

- Do not switch Tabs unless requested by the user or their attention is needed. Creation defaults to `focus=false`; list, screen, and pane input need no prior focus.
- New Tabs use `--no-focus`. Pane creation in a specified Tab attempts to preserve focus without overriding observed concurrent user switches. Callers inspect `focus_verified`, `focus_conflict`, and `degraded`; successful requests do not prove verified focus.
- `return_tab_id` is an explicit restoration target. Do not routinely pass a stale focus snapshot that overrides the user's new selection.
- Once a task's Tab/pane is confirmed exited or complete and retention was not requested, collect needed results, promptly refresh state, and close the smallest safe scope. Close an entire Tab only after checking every pane.
- Preserve unrelated, running, or retained work. Neither a quiet screen nor `accepted=true` proves completion. Verify or ask when state or ownership is unclear; do not guess before closing.
- These are MCP-provided caller guidelines. They do not add background cleanup, completion detection, or user-attention detection. Server-side `force=true` and current MCP resource protections remain in effect.

## Input and screen

- `pane_write_text.text` is required and invokes `write-chars`.
- `pane_send_key.key` is required and invokes restricted `send-keys`.
- The key enum includes Enter, Tab, editing/navigation keys, F1 through F12, Ctrl-C, Ctrl-D, and Escape.
- Ctrl-C, Ctrl-D, and Escape map to zellij `Ctrl c`, `Ctrl d`, and `Esc`, each sent as one argument.
- `pane_screen.full` selects viewport or full scrollback.
- `pane_screen.ansi` controls ANSI preservation.
- Results include `source=zellij_dump_screen`.

## Safety semantics

- Plugin panes cannot enter terminal pane I/O.
- Closing requires explicit `force=true`.
- The current MCP pane and its Tab are protected. Close operations fail closed when the server is inside zellij but its identity is incomplete or stale.
- Missing resources return `workspace_not_found`.
- Unavailable zellij returns `zellij_not_available`.
- Unconfirmed discovery or postconditions return `internal_error`.
- `pane_close` does not expand pane-level authorization into proactively deleting an entire session.
