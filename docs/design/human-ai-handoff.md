# Direct Pane Interaction Boundaries

[中文](human-ai-handoff.cn.md) | [English](human-ai-handoff.md)

## Participants

- The MCP Host operates a specified terminal pane through `pane_write_text`, `pane_send_key`, and `pane_screen`.
- The user observes and operates the same terminal pane through the zellij interface.
- zellij delivers input to the pane program and maintains the terminal display.

## Resource targeting

Each call identifies its target with `session_name + pane_id`. Before writing, callers can refresh session, Tab, title, command, and state information through `workspace_list` or `tab_list`.

## MCP input

The MCP Host should use the two single-purpose input interfaces:

- `pane_write_text.text`: write literal text through `write-chars`.
- `pane_send_key.key`: send one fixed enum key through `send-keys`.

Success means zellij accepted the action. Observe the target program's response with `pane_screen`.

## Human input

Users can type directly in a zellij pane. When the MCP Host and user interact with the same program, inputs are applied in the order they reach zellij.

Preserve the user's Tab focus by default. Discovery, screen reading, and direct pane input do not require focus. Call `tab_focus` or use `focus=true` only at the user's request or when their attention is needed, and explain why. Do not override a concurrent user focus change. `return_tab_id` is an explicit restoration request; a stale focus snapshot does not establish the user's current intent.

## Caller coordination

The caller explicitly organizes workflows requiring human confirmation:

1. Call `workspace_list` or `tab_list` to confirm the target.
2. Call `pane_screen` to read current content.
3. Show the user the information requiring confirmation.
4. After confirmation, call `pane_write_text` or `pane_send_key`.
5. Call `pane_screen` again to inspect the target program's output.

For high-risk commands, verify the session, pane, Tab, title, and command fields before writing, and treat business approval as a separate prerequisite.

## Observation boundaries

- `pane_screen(full=false)` means the current viewport.
- `pane_screen(full=true)` means the full scrollback zellij can export.
- `ansi=true` preserves ANSI escape sequences.
- `truncated=true` indicates truncation at the 262144-character limit.
- Screen text is produced by the pane program and terminal together; callers interpret it according to the target program's protocol.

## Close boundaries

- Closing requires `force=true`.
- Plugin panes cannot be closed as terminal panes.
- The current MCP pane and its containing Tab are protected.
- Callers discover resources before closing and handle the structured close result.
- Once a task's pane/Tab is confirmed exited or complete and the user has not requested retention, save necessary results, promptly refresh state, and close the smallest safe scope. Inspect all panes before closing a whole Tab, preserving unrelated, running, or retained work.
- Accepted input and a quiet screen do not prove completion. Verify or ask when completion or ownership is unclear. The server does not detect task completion or automatically clean resources; these are caller guidelines, not an additional control state machine.
