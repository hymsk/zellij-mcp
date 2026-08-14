# Zellij MCP Direct Pane 架构

[中文](mcp-first.cn.md) | [English](mcp-first.md)

## 目标

`zellij-mcp` 将 zellij 的 session、Tab 和 terminal pane 能力通过默认 stdio 或显式启用的 Streamable HTTP/HTTPS MCP 暴露给兼容的 MCP Host。HTTP 默认仅监听本机，也可由用户为可信网络配置监听地址和访问白名单。MCP 层负责参数校验、资源发现、zellij action 调用和有界返回。

## 拓扑

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

## 组件职责

### MCP Host

- 启动 `zellij-mcp serve`。
- 或连接单独启动的 Streamable HTTP `/mcp` 端点，并附带认证头；HTTP 连接不负责启动 server。
- 通过 `tools/list` 发现 11 个 tools。
- 通过 `tools/call` 传入结构化参数并处理结构化结果。
- 在修改现有资源前调用 `workspace_list` 或 `tab_list`。

### MCP Server

- `MCPProtocol` 处理 stdio JSON-RPC、通知、响应封装和响应字节上限。
- `ToolRuntime` 校验 required、类型、枚举、长度、UTF-8 字节数和未知字段。
- `ToolRuntime` 将精确的 11 个 tool 分派给 workspace、Tab 与 pane handler，并断言 catalog 与 handler 集合一致。
- `tool_catalog.py` 是名称、描述、input schema 和 MCP annotations 的唯一运行时来源。
- HTTP transport 在进入协议与工具层前验证认证、精确 Host/Origin 白名单、媒体类型、协议版本和请求大小，不绕过现有工具安全检查。
- listener 只接受显式 IPv4/IPv6 地址；native TLS 在同一 socket 上使用 TLS 1.2+ `SSLContext`。`0.0.0.0`/`::` 只改变 bind 范围，不扩大 HTTP authority 白名单。传输选择与安全边界见 [HTTP ADR](../decisions/0004-streamable-http.cn.md)。

### ZellijDriver

- 发现活动 session、Tab 和 pane。
- 规范化 `terminal_N` 与 `plugin_N` pane ID。
- 以 argv 方式调用 zellij action。
- 在关闭后重新发现资源以确认结果。
- subprocess 仅通过 `ZellijCommandRunner`；纯 session、Tab 与 pane 输出解析由 `ZellijDiscovery` 完成。

### zellij

- 维护 session、Tab、pane 和 pane 内程序。
- 在 pane 中直接启动 `command`。
- 执行 `write-chars`、`send-keys`、`dump-screen` 和关闭 action。

## 资源模型

### Session

session 使用 `session_name` 标识。调用方可以显式指定 session；当只有一个可选 session 或 MCP 位于 zellij 内时，server 可以解析默认目标。

### Tab

Tab 使用稳定的非负整数 `tab_id` 标识。创建、聚焦、重命名和关闭都以 `tab_id` 为目标。指定 Tab 创建 pane 时使用 zellij `new-pane --tab-id`。

### Pane

terminal pane 使用 `terminal_N`，plugin pane 使用 `plugin_N`。可操作 terminal pane 的完整引用是：

```text
session_name + pane_id
```

`workspace_list` 分别返回 `total_pane_count`、`pane_count`、`terminal_pane_count` 和 `plugin_pane_count`。

## 创建流程

`workspace_create` 接受非空 argv `command`：

1. 校验 `request_id`、`command`、`cwd`、`environment`、模式和 Tab 参数。
2. `auto` 在当前 zellij session 或显式 session 可用时选择 `new-tab`，否则选择 `new-session`。
3. `new-pane` 在目标 session 或目标 Tab 创建 pane。
4. `new-session` 创建后台 session，并将 command 作为初始 terminal pane 程序。
5. 按创建模式返回适用的 `session`、`pane_id`、`tab_id`、`workspace_ref` 和 attach hint。

`environment` 通过结构化 map 接收，并由 argv 形式的 `env` 命令应用。command 不通过 shell 字符串拼接。

## Pane I/O

### 写入

新调用使用两个单用途 tool：

- `pane_write_text` 要求 `text`，调用 `write-chars`。
- `pane_send_key` 要求 `key`，调用 `send-keys`，取值来自固定枚举。
- 返回 `written`、`accepted`、`session`、`pane_id`、`kind` 和写入字节数。

写入结果表示 zellij 接受 action。调用方可以随后使用 `pane_screen` 观察 pane 内容。

### Screen

`pane_screen` 调用 `dump-screen`：

- `full=false` 读取 viewport。
- `full=true` 读取 full scrollback。
- `ansi=false` 返回清理 ANSI 后的文本。
- `ansi=true` 保留 ANSI escape sequence。
- 文本上限为 262144 个字符，超限时保留末尾并设置 `truncated=true`。

## 关闭安全

- `pane_close` 与 `tab_close` 都要求 `force=true`。
- plugin pane 不能进入 terminal pane 写入、读取或关闭路径。
- `pane_close` 拒绝当前 MCP pane。
- `tab_close` 拒绝包含当前 MCP pane 的 Tab。
- 关闭前重新发现目标，关闭后确认 pane、Tab 或 session 状态。
- 发现失败或关闭结果无法确认时返回错误。

## Host 上下文

server 启动时可以从同 uid Linux 祖先进程恢复经过白名单校验的 zellij 环境变量，使当前 session 与 pane 可被 doctor 和资源解析使用。用户在 Host 配置中以 `zellij-mcp serve` 启动 server；本项目不修改任何 Host 配置。

## 接口边界

需求、公开行为与验收标准统一由根 [SPEC.md](../../SPEC.md) 定义，详细字段见 [MCP Tools 参考](../reference/mcp-tools.cn.md)，验证映射见 [覆盖矩阵](../testing/requirements-coverage.cn.md)。

依赖方向固定为：

```text
cli -> protocol facade / diagnostics
cli -> HTTP listener/TLS/allowlist configuration
main -> protocol / tool runtime / HTTP transport
tool runtime -> tool catalog / ZellijDriver
ZellijDriver -> command runner / discovery parser
```
