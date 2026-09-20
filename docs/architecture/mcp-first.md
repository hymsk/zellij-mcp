# Zellij MCP Direct Pane Architecture

[中文](mcp-first.cn.md) | [English](mcp-first.md)

## Goals

`zellij-mcp` exposes zellij sessions, Tabs, and terminal panes to compatible MCP Hosts through default stdio or explicitly enabled Streamable HTTP/HTTPS. HTTP listens locally by default; users can configure a listener and allowlists for trusted networks. The MCP layer validates arguments, discovers resources, invokes zellij actions, and returns bounded results.

## Topology

```text
MCP Host
   |
stdio / Streamable HTTP JSON-RPC
   |
MCPProtocol
   |
ToolRuntime
   |
ZellijDriver
   |
ZellijCommandRunner + ZellijDiscovery
   |
zellij session / Tab / terminal pane
```

## Component responsibilities

### MCP Host

- Launch `zellij-mcp serve`.
- Alternatively, connect to a separately started Streamable HTTP `/mcp` endpoint with authentication headers. An HTTP connection does not start the server.
- Discover 11 tools through `tools/list`.
- Send structured arguments through `tools/call` and handle structured results.
- Call `workspace_list` or `tab_list` before modifying existing resources.

### MCP Server

- `MCPProtocol` handles stdio JSON-RPC, notifications, response wrapping, and response byte limits.
- `ToolRuntime` validates required fields, types, enums, lengths, UTF-8 byte counts, and unknown fields.
- `ToolRuntime` dispatches exactly 11 tools to workspace, Tab, and pane handlers and asserts that the catalog and handler sets match.
- `tool_catalog.py` is the sole runtime source for names, descriptions, input schemas, and MCP annotations.
- Before entering the protocol and tool layers, the HTTP transport validates authentication, exact Host/Origin allowlists, media types, protocol versions, and request size. It does not bypass tool safeguards.
- The listener accepts explicit IPv4/IPv6 addresses only. Native TLS uses a TLS 1.2+ `SSLContext` on the same socket. `0.0.0.0`/`::` change only the bind scope, not the HTTP authority allowlist. See the [HTTP ADR](../decisions/0004-streamable-http.md) for transport choices and security boundaries.

### ZellijDriver

- Discover active sessions, Tabs, and panes.
- Normalize `terminal_N` and `plugin_N` pane IDs.
- Invoke zellij actions using argv.
- Rediscover resources after closing to verify the result.
- Execute subprocesses only through `ZellijCommandRunner`; `ZellijDiscovery` performs pure parsing of session, Tab, and pane output.

### zellij

- Maintain sessions, Tabs, panes, and programs running in panes.
- Launch `command` directly in a pane.
- Execute `write-chars`, `send-keys`, `dump-screen`, and close actions.

## Resource model

### Session

A session is identified by `session_name`. Callers may specify it explicitly. The server can resolve a default target when only one session is available or when MCP runs inside zellij.

### Tab

A Tab is identified by a stable nonnegative integer `tab_id`. Creation, focus, rename, and close target this ID. Creating a pane in a specified Tab uses zellij `new-pane --tab-id`.

### Pane

Terminal panes use `terminal_N`; plugin panes use `plugin_N`. A complete reference to an operable terminal pane is:

```text
session_name + pane_id
```

`workspace_list` returns `total_pane_count`, `pane_count`, `terminal_pane_count`, and `plugin_pane_count` separately.

## Creation flow

`workspace_create` accepts a nonempty argv `command`:

1. Validate `request_id`, `command`, `cwd`, `environment`, mode, and Tab parameters.
2. `auto` selects `new-tab` when a current zellij session or explicit session is available; otherwise it selects `new-session`.
3. `new-pane` creates a pane in the target session or Tab.
4. `new-session` creates a background session with command as the initial terminal pane program.
5. Return `session`, `pane_id`, `tab_id`, `workspace_ref`, and an attach hint as applicable to the mode.

`environment` is a structured map applied through argv-form `env`. Commands are not assembled by shell string concatenation.

## Pane I/O

### Writing

New calls use two single-purpose tools:

- `pane_write_text` requires `text` and invokes `write-chars`.
- `pane_send_key` requires `key` and invokes `send-keys` with a value from a fixed enum.
- Return `written`, `accepted`, `session`, `pane_id`, `kind`, and the written byte count.

A write result means zellij accepted the action. Callers can then observe pane content with `pane_screen`.

### Screen

`pane_screen` invokes `dump-screen`:

- `full=false` reads the viewport.
- `full=true` reads full scrollback.
- `ansi=false` returns text with ANSI escapes removed.
- `ansi=true` preserves ANSI escape sequences.
- Text is limited to 262144 characters; overflow retains the tail and sets `truncated=true`.

## Close safety

- Both `pane_close` and `tab_close` require `force=true`.
- Plugin panes cannot enter terminal pane write, read, or close paths.
- `pane_close` rejects the current MCP pane.
- `tab_close` rejects the Tab containing the current MCP pane.
- Rediscover targets before closing and verify pane, Tab, or session state afterward.
- Return an error if discovery fails or the close outcome cannot be confirmed.

## Host context

At startup, the server can recover allowlisted zellij environment variables from Linux ancestor processes with the same UID, allowing doctor and resource resolution to use the current session and pane. Users configure their Host to launch `zellij-mcp serve`; this project does not modify Host configuration.

## Interface boundaries

The root [SPEC](../../SPEC.md) defines requirements, public behavior, and acceptance criteria. Field details are in the [MCP tools reference](../reference/mcp-tools.md); verification mappings are in the [coverage matrix](../testing/requirements-coverage.md).

Dependency direction is fixed:

```text
cli -> protocol facade / diagnostics
cli -> HTTP listener/TLS/allowlist configuration
main -> protocol / tool runtime / HTTP transport
tool runtime -> tool catalog / ZellijDriver
ZellijDriver -> command runner / discovery parser
```
