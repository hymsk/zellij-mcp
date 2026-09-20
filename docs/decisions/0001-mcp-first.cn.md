# ADR 0001：MCP 作为 Zellij 操作接口

[中文](0001-mcp-first.cn.md) | [English](0001-mcp-first.md)

## 状态

已接受

## 决策

- Codex、OpenCode 和 Claude Code 通过本地 stdio MCP 调用 zellij 能力。
- session、Tab 和 pane 的正式产品操作入口是 MCP tools。
- zellij 是项目支持的终端复用器。
- tool handler 负责结构化校验、资源发现、action 调用和错误映射。
- 调用方在修改现有 pane 前调用 `workspace_list`，在修改 Tab 前调用 `tab_list`。

## 结果

- Host 使用同一 tool catalog 与 JSON-RPC 行为。
- zellij action 参数保持 argv 结构。
- 资源枚举失败与后置条件不明确时采用 fail-closed 处理。
