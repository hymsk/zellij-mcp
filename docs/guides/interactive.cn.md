# Direct Pane 操作指南

[中文](interactive.cn.md) | [English](interactive.md)

## 连接检查

Host 连接后先调用：

```text
zellij_mcp_doctor
```

确认 `capabilities.zellij`、`zellij_stable_tab_control` 和 `zellij_direct_pane_io` 满足当前操作。

## 发现资源

查看当前 session：

```json
{
  "session_name": "dev",
  "all_sessions": false,
  "include_plugins": true
}
```

调用 `workspace_list` 后保存目标 `session` 与 `pane_id`。需要 Tab 信息时调用 `tab_list`。

## 创建 Pane

在指定 session 中创建 shell：

```json
{
  "request_id": "shell-001",
  "command": ["/bin/sh"],
  "workspace_type": "new-pane",
  "session_name": "dev"
}
```

创建独立 session：

```json
{
  "request_id": "session-001",
  "command": ["/bin/sh"],
  "workspace_type": "new-session",
  "session_name": "zellij-mcp-demo"
}
```

创建结果返回 `session`、`pane_id`、`tab_id` 和 `attach_hint`。

## 写入 Pane

写入文本：

```json
{
  "session_name": "zellij-mcp-demo",
  "pane_id": "terminal_0",
  "text": "printf 'hello\\n'"
}
```

发送 Enter：

```json
{
  "session_name": "zellij-mcp-demo",
  "pane_id": "terminal_0",
  "key": "Enter"
}
```

使用 `pane_write_text` 写入文本，使用 `pane_send_key` 发送按键。

## 读取 Pane

读取 viewport：

```json
{
  "session_name": "zellij-mcp-demo",
  "pane_id": "terminal_0",
  "full": false,
  "ansi": false
}
```

读取 full scrollback 并保留 ANSI：

```json
{
  "session_name": "zellij-mcp-demo",
  "pane_id": "terminal_0",
  "full": true,
  "ansi": true
}
```

检查返回的 `truncated`。文本超过 262144 个字符时，结果保留末尾内容。

## Tab 操作

1. 调用 `tab_list` 获取稳定 `tab_id`。
2. 调用 `workspace_create(workspace_type="new-tab")` 创建 Tab。
3. 调用 `workspace_create`，指定 `workspace_type="new-pane"`、`session_name` 和 `tab_id`，将 pane 直接创建到目标 Tab。
4. 调用 `tab_focus` 或 `tab_rename` 修改目标 Tab。
5. 调用 `tab_close(force=true)` 关闭目标 Tab。

## 安全关闭

关闭 pane：

```json
{
  "session_name": "zellij-mcp-demo",
  "pane_id": "terminal_0",
  "force": true
}
```

关闭前再次调用 `workspace_list` 或 `tab_list`。plugin pane、当前 MCP pane 及包含当前 MCP pane 的 Tab 会被拒绝。
