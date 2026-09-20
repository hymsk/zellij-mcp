# ADR 0003：Direct Pane Runtime

[中文](0003-direct-pane-runtime.cn.md) | [English](0003-direct-pane-runtime.md)

## 状态

已接受

## 决策

- zellij session、Tab 和 terminal pane 构成运行资源。
- terminal pane 通过 `session_name + pane_id` 定位。
- `workspace_create` 在 pane、Tab 或 session 中直接运行 argv `command`。
- `workspace_list` 与 `tab_list` 从 zellij 读取实时资源。
- `pane_write_text` 使用 `write-chars`，`pane_send_key` 使用固定枚举的 `send-keys`。
- `pane_screen` 使用 `dump-screen`，支持 viewport、full scrollback 与 ANSI 选项。
- screen 文本最多返回 262144 个字符。
- `pane_close` 与 `tab_close` 要求 `force=true`，并保护 plugin pane 与当前 MCP pane。
- 精确 pane 与 Tab 操作显式要求 `session_name`；list tools 可使用当前或唯一 session 作为发现便利。
- `pane_close` 不主动删除 session，避免将 pane 级授权扩大为 session 级删除。
- MCP 协议、tool runtime、zellij subprocess 和 discovery 解析使用独立模块；公共 facade 保持 `ZellijMCPServer`。
- wheel 内嵌构建时的完整源码 commit 与 dirty 状态，`version --json` 和 doctor 可查询该 provenance。

## 资源不变量

- session 名称在 zellij 活动 session 集合中解析。
- Tab 操作使用稳定 `tab_id`。
- terminal 与 plugin pane 使用独立 ID 空间。
- 修改资源前执行发现，关闭资源后确认结果。
- 未知资源状态返回错误。

## Tool Surface

公开 tools 精确为：

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

所有 tools 显式提供四个 MCP behavior hints：`readOnlyHint`、`destructiveHint`、
`idempotentHint` 和 `openWorldHint`。Hints 只描述行为，不扩大权限或弱化安全检查。
