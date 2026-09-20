# 功能基线

[中文](features.cn.md) | [English](features.md)

本文按功能说明根 [SPEC.md](../../SPEC.md) 定义的当前行为；需求与验收标准统一在 SPEC 维护。

## 精确 Tool 集合

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

## 能力矩阵

| 能力 | 行为 |
|------|------|
| stdio MCP | 支持 initialize、notifications、ping、tools/list、tools/call 和结构化错误 |
| Streamable HTTP MCP | 显式启用、默认 loopback，可绑定具体 IPv4/IPv6 或 wildcard；单一 `/mcp` 端点，通过 POST 返回 JSON，GET 不提供 SSE |
| HTTP 安全 | 必需 Bearer token、显式 Host/Origin 白名单、有界请求；非 loopback 明文 HTTP 会警告 |
| 原生 HTTPS | 成对 PEM certificate/key，标准库 `SSLContext` server TLS 最低 1.2；不新增运行时依赖 |
| Tool annotations | 11 个 tools 显式提供 read-only、destructive、idempotent 与 open-world hints |
| 使用端指导 | initialize 指引及 tool/参数描述明确焦点保护、任务结束后的及时清理、资源定位、输入与完成的区别；所有顶层参数有文字说明，boolean 与创建模式声明真实默认值 |
| 参数边界 | 校验类型、required、枚举、长度、UTF-8 字节数与未知字段 |
| doctor | 检查 Python、zellij、后台创建、稳定 Tab、direct pane I/O 与当前上下文 |
| session 发现 | 枚举活动 session，并区分空集合与发现失败 |
| pane 发现 | 返回 terminal/plugin pane 明细与四类计数 |
| workspace 创建 | 创建 pane、Tab 或 session，并直接运行 argv command |
| environment | 通过结构化 map 应用到 command |
| Tab 管理 | 通过 `workspace_create(new-tab)` 创建，并使用稳定 `tab_id` 列出、聚焦、重命名和关闭 |
| 指定 Tab 创建 | 使用 `new-pane --tab-id` 将 pane 创建到目标 Tab，并重新发现确认归属 |
| pane 写入 | 使用独立的 `pane_write_text` 与 `pane_send_key` |
| pane screen | 使用 `dump-screen` 读取 viewport 或 full，可保留 ANSI |
| screen 上限 | 最多返回 262144 个字符，并受 stdio 响应字节上限约束，超限时设置 `truncated=true` |
| pane 关闭 | 要求 `force=true`，保护 plugin pane 与当前 MCP pane，当前身份不完整时拒绝 |
| Tab 关闭 | 要求 `force=true`，保护包含当前 MCP pane 的 Tab，当前身份不完整时拒绝 |
| 安装 provenance | wheel 内嵌完整源码 commit 与已跟踪文件 dirty 状态；version/doctor JSON 可查询 |

## 资源引用

terminal pane 的调用参数使用：

```json
{
  "session_name": "dev",
  "pane_id": "terminal_3"
}
```

`workspace_list` 与 `tab_list` 是资源发现入口。调用方使用 list 结果获取 session、Tab、pane、标题、命令、cwd、状态和几何信息。

精确 pane 与 Tab 操作必须显式提供 `session_name`，避免 session 局部 ID 解析到错误资源。

## MCP Annotations

- `zellij_mcp_doctor`、`workspace_list`、`tab_list`、`pane_screen` 是只读且幂等的 closed-world tools。
- `tab_focus` 与 `tab_rename` 是非破坏、幂等的 closed-world mutations。
- `workspace_create`、`pane_write_text`、`pane_send_key`、`tab_close` 与 `pane_close` 标记为 destructive/open-world，且不声明跨进程幂等。
- `workspace_create.request_id` 只提供单个工具运行时内的有限缓存；stdio 中限于当前进程，HTTP 中限于当前 MCP session，不等价于跨 session 或跨进程幂等保证。

## 创建语义

- `workspace_type=auto` 根据当前 zellij 上下文与显式 session 选择模式；优先使用现有 session 创建 Tab，否则创建新 session。
- `workspace_type=new-pane` 在目标 session 创建 pane。
- `workspace_type=new-tab` 在目标 session 创建新 Tab；默认模式实际为 `auto`，按上下文选择。
- `workspace_type=new-session` 创建新的后台 session；显式同名 session 已存在时拒绝。
- `command` 是非空 argv 数组。
- `cwd` 是可选工作目录。
- `environment` 是可选字符串 map。
- `request_id` 为创建调用提供进程内幂等键；缓存达到固定上限时拒绝新的创建 ID，不驱逐已有结果。
- 可以确认 action 未发生的失败不会占用 `request_id`；action 结果未知时保留 unresolved 状态，阻止不安全重试。

## 焦点与生命周期指导

- 用户未要求、且没有确需用户关注的情况时，不主动切换 Tab。创建默认 `focus=false`；list、screen 和 pane 输入不需要先聚焦。
- 新 Tab 使用 `--no-focus`；指定 Tab 创建 pane 时尝试保持原焦点，不覆盖已观测到的用户并发切换。调用方检查 `focus_verified`、`focus_conflict`、`degraded`，不将请求成功等同于焦点验证成功。
- `return_tab_id` 是显式恢复目标，不应常规传入旧焦点快照而覆盖用户的新选择。
- 本任务相关 Tab/pane 已确认退出或处理完成、且用户未要求保留时，先提取必要结果，再及时刷新状态并关闭最小安全范围；整个 Tab 只有在检查全部 pane 后才可关闭。
- 保留无关、仍在运行或用户要求保留的工作；安静屏幕和 `accepted=true` 都不能证明完成。状态或归属不明时先核实或询问，不猜测关闭。
- 这些是 MCP 提供给调用方的指导，不新增后台清理、完成检测或用户注意力判定逻辑。服务端原有 `force=true` 与当前 MCP 资源保护保持不变。

## 写入与 Screen

- `pane_write_text.text` 是必填字段，调用 `write-chars`。
- `pane_send_key.key` 是必填字段，调用受限 `send-keys`。
- key 枚举包含 Enter、Tab、编辑键、方向键、F1 到 F12、Ctrl-C、Ctrl-D 和 Escape。
- Ctrl-C、Ctrl-D 和 Escape 会映射到 zellij 的 `Ctrl c`、`Ctrl d` 和 `Esc`，每个组合键作为单个参数发送。
- `pane_screen.full` 控制 viewport 或 full scrollback。
- `pane_screen.ansi` 控制 ANSI 保留。
- 返回 `source=zellij_dump_screen`。

## 安全语义

- plugin pane 不能进入 terminal pane I/O。
- 关闭必须显式设置 `force=true`。
- 当前 MCP pane 和对应 Tab 受保护；server 位于 zellij 内但身份不完整或失效时，关闭操作 fail-closed。
- 资源不存在时返回 `workspace_not_found`。
- zellij 不可用时返回 `zellij_not_available`。
- 发现或后置条件无法确认时返回 `internal_error`。
- `pane_close` 不会把 pane 级授权扩大为主动删除整个 session。
