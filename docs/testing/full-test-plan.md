# Direct Pane Full Test Plan

[中文](full-test-plan.cn.md) | [English](full-test-plan.md)

## Goals

Use the root [SPEC](../../SPEC.md) as the acceptance baseline, covering MCP protocol, HTTP/HTTPS, strict schemas, zellij resource discovery, workspace creation, Tab lifecycle, pane I/O, and safe closing. Hosts either start `zellij-mcp serve` over stdio or connect to an explicitly started HTTP `/mcp` endpoint, using the same discovery and I/O acceptance steps.

## Test layers

| Gate | Scope | Pass criteria |
|------|-------|---------------|
| G0 | Documentation and static constraints | Valid links, matching SPEC/coverage requirement IDs, matching SPEC/bilingual README/tool catalog names, passing diff checks |
| G1 | Unit tests | Passing JSON-RPC, HTTP/HTTPS loopback, schema, handler, and driver cases |
| G2 | stdio and installed artifacts | Passing initialize, tools/list, tools/call, annotations, errors, stdout boundaries, and wheel provenance |
| G3 | Isolated real zellij | Installed wheel passes session, Tab, and pane create/list/write/screen/close paths with no leftover sessions |

## MCP and schemas

| ID | Scenario | Expected result |
|----|----------|-----------------|
| DP-PROTO-001 | Initialize and initialized notification | Return serverInfo, capability, and compatible protocol |
| DP-PROTO-002 | Ping and tools/list | Successful ping and exactly 11 tools |
| DP-PROTO-003 | Successful tools/call | Text content and structuredContent represent the same result |
| DP-PROTO-004 | Tool error | Return `isError=true` with stable code/message/details |
| DP-PROTO-005 | Unknown method or tool | Corresponding protocol error or `invalid_argument` |
| DP-PROTO-006 | Notification without ID | No response; request methods also produce no side effects |
| DP-PROTO-007 | Invalid JSON and oversized request | Bounded rejection; subsequent requests remain processable |
| DP-PROTO-008 | stdout boundary | stdout contains JSON-RPC messages only |
| DP-PROTO-009 | Deeply nested JSON | Parse error; subsequent requests remain processable |
| DP-PROTO-010 | Multibyte screen response | tools/call retains the tail within the response byte limit |
| DP-PROTO-011 | Installed tools/list | Installed wrapper in temporary venv returns exactly 11 tools with complete schemas and annotations |
| DP-PROTO-012 | Wheel provenance | Version JSON source_commit/source_dirty match build inputs |
| DP-ARG-001 | Missing required field or wrong type | `invalid_argument` before action |
| DP-ARG-002 | Unknown field | Rejected before action |
| DP-ARG-003 | NUL, oversized identifier, or cwd | Rejected before action |
| DP-ARG-004 | Command item count, item size, or total byte limit exceeded | Rejected before action |
| DP-ARG-005 | Invalid environment keys, values, count, or total bytes | Rejected before action |
| DP-ARG-006 | Crossed fields in split pane input | Rejected before action |
| DP-ARG-007 | pane_send_key key outside enum | Rejected before action |
| DP-ARG-008 | Out-of-range Tab ID or conflicting parameters | Rejected before action |
| DP-ARG-009 | Missing session_name for exact pane/Tab operations | Rejected before action; no inferred destructive target |

## Zellij resources

| ID | Scenario | Expected result |
|----|----------|-----------------|
| DP-ZELLIJ-001 | zellij unavailable | Doctor reports missing capabilities; resource operations return stable errors |
| DP-ZELLIJ-002 | Background creation capability | Doctor returns `supports_background_create` |
| DP-ZELLIJ-003 | Stable Tab action capability | Doctor returns `supports_stable_tab_control` |
| DP-ZELLIJ-004 | Direct pane I/O capability | Doctor returns `supports_direct_pane_io` |
| DP-ZELLIJ-005 | Current session and pane | Normalize to session and `terminal_N` |
| DP-ZELLIJ-006 | Single-session default resolution | Select the sole session when omitted |
| DP-ZELLIJ-007 | Multiple sessions without a default target | Require `session_name` or `all_sessions=true` |
| DP-ZELLIJ-008 | terminal_0 and plugin_0 coexist | Preserve both panes with explicit types |
| DP-ZELLIJ-009 | Session or pane enumeration failure | Error instead of a false empty collection |
| DP-ZELLIJ-010 | workspace_list aggregation | All four pane counts agree with details |

## Workspaces and Tabs

| ID | Scenario | Expected result |
|----|----------|-----------------|
| DP-WS-001 | Create new-pane | Command, cwd, and environment match the returned pane |
| DP-WS-002 | Create new-session | Command becomes the initial terminal pane program |
| DP-WS-003 | Auto mode | Select Tab or session according to context |
| DP-WS-004 | Repeated request_id | Same result or explicit conflict; no duplicate creation |
| DP-WS-005 | Specified session | Pane is created in the explicit session |
| DP-WS-006 | Specified tab_id | Pane is created directly in the target Tab and membership is rechecked |
| DP-WS-007 | new-session name already exists | Rejected before action; no fallback to new-pane |
| DP-WS-008 | Creation failure before action | request_id can be safely reused; unknown outcomes retain unresolved state |
| DP-WS-009 | New Tab creation and focus restoration | New Tab runs command; with `focus=false` and valid `return_tab_id`, restore that session's target Tab |
| DP-WS-010 | Invalid return_tab_id | new-tab or targeted new-pane returns `workspace_not_found` before action with no resource creation |
| DP-TAB-001 | tab_list | Stable IDs, active-state source, and pane membership |
| DP-TAB-002 | workspace_create new-tab | New `tab_id` and structured Tab information |
| DP-TAB-003 | tab_focus | Confirm target active state when observable |
| DP-TAB-004 | tab_rename | Change and verify the name by stable ID |
| DP-TAB-005 | tab_close without force | `permission_denied` |
| DP-TAB-006 | tab_close on a protected Tab | `permission_denied`; resource remains |
| DP-TAB-007 | tab_close on a normal target | Verify Tab or session state and return resources |

## Pane I/O and closing

| ID | Scenario | Expected result |
|----|----------|-----------------|
| DP-PANE-001 | pane_write_text | Invoke `write-chars` for the target pane |
| DP-PANE-002 | pane_send_key | Map public key to one zellij `send-keys` argument |
| DP-PANE-003 | Write to a plugin pane | `permission_denied` |
| DP-PANE-004 | Viewport screen | `full=false` returns viewport |
| DP-PANE-005 | Full screen | `full=true` returns full scrollback |
| DP-PANE-006 | ANSI option | True preserves escapes; false removes them |
| DP-PANE-007 | Oversized screen | Retain the last 262144 characters and set `truncated=true` |
| DP-PANE-008 | pane_close without force | `permission_denied` |
| DP-PANE-009 | Close plugin pane or current MCP pane | `permission_denied` |
| DP-PANE-010 | pane_close on a normal target | Rediscover and confirm after closing |
| DP-PANE-011 | Unknown post-close state | `internal_error` |
| DP-PANE-012 | Incomplete or stale current MCP identity | Both pane_close and tab_close fail closed |
| DP-PANE-013 | Last terminal pane | Close only the pane; do not proactively delete a plugin-only session |

## Resource cleanup

Real zellij scenarios use unique session names, Tab names, and pane titles. At the end, call list tools to confirm test resource state and record protected-target rejections.

## Execution constraints

- Unit tests use isolated HOME and temporary directories.
- Real zellij and Host scenarios require explicit execution.
- Real lifecycle tests use independent HOME, XDG directories, and a short `ZELLIJ_SOCKET_DIR`.
- Lifecycle tests start MCP through an installed wheel rather than importing the runtime from source.
- Reports distinguish executed, not executed, and environment-blocked checks.
