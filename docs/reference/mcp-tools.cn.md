# MCP Tools 参考

[中文](mcp-tools.cn.md) | [English](mcp-tools.md)

本文是根 [SPEC.md](../../SPEC.md) 的详细接口参考。schema 的唯一运行时来源为 [`zellij_mcp/server/tool_catalog.py`](../../zellij_mcp/server/tool_catalog.py)。公开 tool 集合精确为 11 个，本文、SPEC 和实际 tools/list 必须一致。

## 通用约定

- tool arguments 必须是 object。
- 未声明字段拒绝。
- identifier 最长 256 个字符。
- `cwd` 最长 4096 个字符。
- command 最多 256 项，总 UTF-8 大小最多 512 KiB。
- environment 最多 256 项，总 UTF-8 大小最多 65536 bytes。
- `pane_write_text.text` 最多 65536 个字符且最多 65536 UTF-8 bytes。
- pane 资源使用 `session_name + pane_id` 定位。
- 精确 pane 与 Tab 操作必须显式传入 `session_name`；只有 list tools 和创建目标解析可使用默认 session。
- 修改现有 pane 或 Tab 前先调用 list tool。
- `workspace_type=new-session` 要求目标 session 尚不存在。
- `workspace_type` 默认 `auto`：在 zellij 内或提供 `session_name` 时选择 `new-tab`，否则选择后台 `new-session`。
- `workspace_type=new-pane` 在目标 session 创建新 pane。
- server 位于 zellij 内但无法确认当前 MCP pane 身份时，关闭操作拒绝执行。

## 使用端操作指导

1. **先发现、后操作**：使用 list 返回的 `session_name + pane_id/tab_id`；`pane_id` 例如 `terminal_3`，`tab_id` 是稳定 ID，不是显示位置。不要猜测 ID。部分发现失败时检查 `degraded/failed_sessions`。
2. **默认不切焦点**：用户未要求、且非确需用户关注的情况，不调用 `tab_focus`，创建保持 `focus=false`。发现、读屏、输入都无需先切换 Tab。确需聚焦时向用户说明原因；不要反复“恢复”旧焦点而覆盖用户的并发选择。
3. **确认完成后及时清理**：本任务相关 pane/Tab 已退出或处理完成且用户未要求保留时，先收集必要输出，再刷新发现结果并及时关闭。优先 `pane_close`；仅确认 Tab 内全部工作都可清理时使用 `tab_close`。无关、仍在运行或需保留的工作不能一并关闭；归属或完成状态不明时先核实或询问。
4. **不以安静代替完成证据**：`accepted=true` 仅说明输入被接受；屏幕快照或短暂无输出不证明命令退出。按目标程序的完成信息结合任务上下文判断，并在关闭后检查 `verified/session_closed`。

`initialize.instructions` 只提供选择条件与最小共用约束：用户要求 zellij，或需要持久交互终端、后台终端任务、已配置远程服务的终端访问时使用；其他场景优先使用 Host 常规执行工具。相关工具的 `description` 保留操作与安全指导，`workspace_create` 同时说明持久交互和后台终端任务用途。所有顶层参数都有 `description`，boolean 与 `workspace_type` 提供 schema `default`。默认值描述既有运行时行为，不由 schema 自动填参。Host 是否向模型注入指引、annotations 和参数说明取决于 Host；`tools/list` 仍返回全部 11 个工具，并非渐进加载。当前没有 `outputSchema`、resources 或 prompts，返回字段参考仍见本文及工具描述。

这些规则不代表服务端自动识别任务完成或自动关闭资源。关闭仍须显式传 `force=true`，并受既有身份保护约束；关闭活动 Tab 或最后一个 pane 可能由 zellij 自身改变可见焦点或结束 session。

描述优先保留用途、安全和参数组合语义，不重复 schema 类型、长度或默认值。详细契约仍见下文；精简描述不改变运行行为，也不按需加载工具。

## 1. zellij_mcp_doctor

检查 Python、zellij、direct pane I/O 和服务端 zellij 上下文。不独立验证 Host 配置或权限策略，`capabilities.host` 为 `not_checked`。

参数：空 object。

主要返回字段：`ok`、`zellij-mcp`、`python`、`zellij`、`capabilities`、`warnings`、`fixes`。

## 2. workspace_create

创建 pane、Tab 或 session，并直接运行 argv command。

必填参数：

- `request_id`：非空创建重试键。同一请求以相同参数复用；缓存只限当前 stdio 进程或 HTTP MCP session，不跨重启。结果未知时先发现真实资源，不通过换新 ID 盲目重试。
- `command`：非空 argv 数组，不是 shell 字符串；管道、重定向或展开需显式使用 shell。

可选参数：

- `cwd`：工作目录，建议绝对路径；省略时采用运行时/zellij 上下文，不保证是 Host 的项目目录。
- `environment`：仅针对该命令添加或覆盖环境的字符串 map，省略不添加。
- `workspace_type`：默认 `auto`；可选 `new-pane`、`new-tab`、`new-session`。
- `session_name`：`new-pane/new-tab` 的已有目标 session，省略时选择当前或唯一活动 session；`new-session` 的新名称，省略则生成名称。向 `auto` 提供该字段会选择 `new-tab`。
- `tab_name`：`new-tab` 的可选名称。
- `tab_id`：`new-pane` 的目标稳定 Tab ID；同时必须提供 `session_name`。
- `return_tab_id`：`focus=false` 时恢复的同一 session Tab ID。`new-tab` 可单独使用该字段；`new-pane` 必须同时提供目标 `tab_id`。
- `focus`：默认 false；true 请求聚焦新 Tab 或显式指定的 `new-pane tab_id`，不能与 `return_tab_id` 同时使用。仅用户要求或确需用户关注时设 true。

主要返回字段：`workspace_ref`、`session`、`tab_id`、`pane_id`、`attach_hint`、`direct`、焦点验证字段和 `degraded`。

`workspace_ref` 始终包含 `type` 与 `session`。`type` 为 `session`、`pane` 或 `tab`；session 和 pane 引用包含 `pane`，Tab 引用包含 `tab`。

提供 `tab_id` 时必须同时提供 `session_name`。

`return_tab_id` 必须在创建前已存在于目标 session；不存在时返回 `workspace_not_found`，不会创建 Tab 或 pane。

`new-tab` 返回 `tab_id` 而非 `pane_id`，随后通过 `tab_list` 找到目标 pane。新 Tab 使用 no-focus 创建；指定 Tab 的 new-pane 尝试保持原焦点，调用方仍需检查焦点验证与降级字段。通常省略 `return_tab_id`，避免显式恢复覆盖用户的并发切换。

## 3. workspace_list

列出 live session 与 pane。

参数：

- `session_name`：指定 session，优先于 `all_sessions`；两者均未指定时选当前或唯一活动 session。
- `all_sessions`：默认 false；读取全部活动 session。
- `include_plugins`：默认 false；在 pane 明细中包含 plugin pane，不影响始终报告的 plugin 计数。

主要返回字段：`current_session`、`current_pane`、`session_count`、`total_pane_count`、`pane_count`、`terminal_pane_count`、`plugin_pane_count`、`sessions`、`degraded`、`failed_sessions`。

## 4. tab_list

列出稳定 Tab ID 与 pane 归属。

参数：

- `session_name`：指定 session；未指定且 `all_sessions=false` 时选当前或唯一活动 session。
- `all_sessions`：默认 false；读取全部活动 session，不能与 `session_name` 同时提供。
- `include_panes`：默认 true；在 Tab 明细中包含 terminal/plugin pane。

主要返回字段：`current_session`、`current_pane`、`session_count`、`tab_count`、`sessions`。

每个 Tab 包含 `tab_id`、位置、名称、活动状态来源和 pane 计数。

## 5. tab_focus

按稳定 Tab ID 聚焦 Tab。

此操作改变用户可见焦点；仅用户要求或确需用户关注时使用并说明原因，不为 list、screen 或 pane 输入切焦点。

必填参数：`session_name`、`tab_id`。

主要返回字段：`focused`、`changed`、`session`、`tab_id`、`previous_tab_id`、`focus_verified`、`verified`、`degraded`。

## 6. tab_rename

按稳定 Tab ID 重命名 Tab。

必填参数：`session_name`、`tab_id`、`tab_name`。

主要返回字段：`renamed`、`changed`、`session`、`tab_id`、`previous_name`、`tab`、`verified`、`degraded`。

## 7. tab_close

按稳定 Tab ID 关闭 Tab。

必填参数：`session_name`、`tab_id`。

可选参数：`force`。执行关闭时 `force` 必须为 true。

主要返回字段：`closed`、`session`、`tab_id`、`tab`、`pane_ids`、`resources`、`verified`、`session_closed`。

包含当前 MCP pane 的 Tab 受保护。任务完成且无需保留时及时清理，但须先保存结果并通过 `tab_list(include_panes=true)` 检查全部 pane；仅一个 pane 完成时优先关闭该 pane，避免终止其他工作。

## 8. pane_write_text

向 live terminal pane 写入字面 text。该单用途 schema 避免 Host 将互斥可选字段错误转换为同时必填字段。

必填参数：`session_name`、`pane_id`、`text`。

`text` 调用 `write-chars`，不自动追加 Enter；文本内的换行仍可能提交输入。先确认前台程序，再输入；成功仅表示输入被接受，`completion_verified=false`。

主要返回字段：`written`、`accepted`、`session`、`pane_id`、`kind="text"`、`bytes`、`completion_verified`。

## 9. pane_send_key

向 live terminal pane 发送一个受限 key。

Enter 可能提交命令；Ctrl-C/Ctrl-D 可能中断或退出前台程序。无需切换 Tab，先确认目标，输入被接受不代表命令完成。

必填参数：`session_name`、`pane_id`、`key`。

key 枚举：

```text
Enter Tab Backspace Delete Up Down Right Left Home End PageUp PageDown
F1 F2 F3 F4 F5 F6 F7 F8 F9 F10 F11 F12 Ctrl-C Ctrl-D Escape
```

公开名称 `Ctrl-C`、`Ctrl-D`、`Escape` 分别映射为 zellij 的单个 key specification `Ctrl c`、`Ctrl d`、`Esc`。

主要返回字段：`written`、`accepted`、`session`、`pane_id`、`kind="key"`、`bytes=0`、`completion_verified`。

## 10. pane_screen

读取 live terminal pane 的 screen。

必填参数：`session_name`、`pane_id`。

可选参数：

- `full`：默认 false 读取 viewport，true 读取 full scrollback，仍受截断限制。
- `ansi`：默认 false 去除 ANSI，true 保留 ANSI。

主要返回字段：`session`、`pane_id`、`text`、`full`、`ansi`、`truncated`、`source`。文本先限制为 262144 个字符，stdio tools/call 还会按响应字节上限保留末尾内容。

屏幕无输出不证明进程退出或任务完成，不可仅据此关闭资源。

## 11. pane_close

关闭 live terminal pane。

必填参数：`session_name`、`pane_id`。

可选参数：`force`。执行关闭时 `force` 必须为 true。

主要返回字段：`closed`、`verified`、`session`、`pane_id`、`session_closed`、`resources`。

plugin pane 与当前 MCP pane 受保护。

任务资源已确认退出或完成且用户未要求保留时，保存结果、刷新发现信息并及时关闭；保留无关、仍在运行或用户要求保留的工作，状态不明时不猜测。

`pane_close` 只关闭指定 pane，不主动删除只剩 plugin pane 的 session；如果 zellij 因 pane 消失自行结束 session，返回 `session_closed=true`。

## 错误语义

| Code | 含义 |
|------|------|
| `invalid_argument` | 参数类型、required、枚举、范围、互斥关系或大小不符合 schema |
| `zellij_not_available` | zellij 不可用 |
| `workspace_not_found` | session、Tab 或 pane 不存在 |
| `permission_denied` | force 缺失或目标受保护 |
| `internal_error` | zellij action、资源发现或后置条件确认失败 |
