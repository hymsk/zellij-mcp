# ADR 0001: MCP as the Zellij Interface

[中文](0001-mcp-first.cn.md) | [English](0001-mcp-first.md)

## Status

Accepted.

## Decision

- Codex, OpenCode, and Claude Code use local stdio MCP to access zellij capabilities.
- MCP tools are the formal product interface for session, Tab, and pane operations.
- zellij is the supported terminal multiplexer.
- Tool handlers validate structured arguments, discover resources, call actions, and map errors.
- Callers use `workspace_list` before changing panes and `tab_list` before changing Tabs.

## Consequences

- Hosts share the same tool catalog and JSON-RPC behavior.
- zellij action arguments retain their argv structure.
- Discovery failures and uncertain postconditions fail closed.
