# Direct Pane 全量测试计划

[中文](full-test-plan.cn.md) | [English](full-test-plan.md)

## 目标

测试以根 [SPEC.md](../../SPEC.md) 为验收基线，覆盖 MCP 协议、HTTP/HTTPS、严格 schema、zellij 资源发现、workspace 创建、Tab 生命周期、pane I/O 和安全关闭。Host 通过 stdio 启动 `zellij-mcp serve`，或连接显式启动的 HTTP `/mcp` 端点，并使用同一套 discovery 与 I/O 验收步骤。

## 测试层次

| Gate | 范围 | 通过标准 |
|------|------|----------|
| G0 | 文档与静态约束 | 链接有效、SPEC/覆盖矩阵需求 ID 一致、SPEC/双语 README/tool catalog 名称一致、diff 检查通过 |
| G1 | 单元测试 | JSON-RPC、HTTP/HTTPS loopback、schema、handler 与 driver 用例通过 |
| G2 | stdio 与安装产物 | initialize、tools/list、tools/call、annotations、错误、stdout 边界和 wheel provenance 通过 |
| G3 | 隔离真实 zellij | 已安装 wheel 的 session、Tab、pane create/list/write/screen/close 路径通过且无遗留 session |

## MCP 与 Schema

| ID | 场景 | 预期 |
|----|------|------|
| DP-PROTO-001 | initialize 与 initialized notification | 返回 serverInfo、capability 和兼容 protocol |
| DP-PROTO-002 | ping 与 tools/list | ping 成功，tool 集合精确为 11 个 |
| DP-PROTO-003 | tools/call 成功 | text content 与 structuredContent 表达同一结果 |
| DP-PROTO-004 | tool 错误 | 返回 `isError=true` 与稳定 code/message/details |
| DP-PROTO-005 | 未知 method 或 tool | 返回对应协议错误或 `invalid_argument` |
| DP-PROTO-006 | notification 无 id | 不写响应，request method 也不执行副作用 |
| DP-PROTO-007 | 非法 JSON 与超大请求 | 有界拒绝，后续请求仍可处理 |
| DP-PROTO-008 | stdout 边界 | stdout 只包含 JSON-RPC 消息 |
| DP-PROTO-009 | 深层 JSON | 返回 parse error，后续请求仍可处理 |
| DP-PROTO-010 | 多字节 screen 响应 | tools/call 保留末尾并保持在响应字节上限内 |
| DP-PROTO-011 | 安装后 tools/list | 临时 venv 中已安装 wrapper 精确返回 11 tools、完整 schema 与 annotations |
| DP-PROTO-012 | wheel provenance | version JSON 的 source_commit/source_dirty 与构建输入一致 |
| DP-ARG-001 | required 缺失或类型错误 | action 前返回 `invalid_argument` |
| DP-ARG-002 | 未知字段 | action 前拒绝 |
| DP-ARG-003 | NUL、超长 identifier 或 cwd | action 前拒绝 |
| DP-ARG-004 | command 数量、单项和总字节超限 | action 前拒绝 |
| DP-ARG-005 | environment 键、值、数量或总字节非法 | action 前拒绝 |
| DP-ARG-006 | split pane input 交叉字段 | action 前拒绝 |
| DP-ARG-007 | pane_send_key 的 key 不在枚举 | action 前拒绝 |
| DP-ARG-008 | Tab ID 超界或参数组合冲突 | action 前拒绝 |
| DP-ARG-009 | 精确 pane/Tab 操作缺少 session_name | action 前拒绝，不推断破坏性资源 |

## Zellij 资源

| ID | 场景 | 预期 |
|----|------|------|
| DP-ZELLIJ-001 | zellij 不可用 | doctor 报告能力缺失，资源操作返回稳定错误 |
| DP-ZELLIJ-002 | 后台创建能力检查 | doctor 返回 `supports_background_create` |
| DP-ZELLIJ-003 | 稳定 Tab action 检查 | doctor 返回 `supports_stable_tab_control` |
| DP-ZELLIJ-004 | direct pane I/O 检查 | doctor 返回 `supports_direct_pane_io` |
| DP-ZELLIJ-005 | 当前 session 与 pane | 规范化为 session 与 `terminal_N` |
| DP-ZELLIJ-006 | 单 session 默认解析 | 未传 session 时选择唯一 session |
| DP-ZELLIJ-007 | 多 session 且无默认目标 | 要求 `session_name` 或 `all_sessions=true` |
| DP-ZELLIJ-008 | terminal_0 与 plugin_0 同时存在 | 两个 pane 均保留且类型明确 |
| DP-ZELLIJ-009 | session 或 pane 枚举失败 | 返回错误，不报告虚假空集合 |
| DP-ZELLIJ-010 | workspace_list 聚合 | 四类 pane 计数与明细一致 |

## Workspace 与 Tab

| ID | 场景 | 预期 |
|----|------|------|
| DP-WS-001 | new-pane 创建 | command、cwd、environment 与返回 pane 一致 |
| DP-WS-002 | new-session 创建 | command 成为初始 terminal pane 程序 |
| DP-WS-003 | auto 模式 | 根据上下文选择 Tab 或 session |
| DP-WS-004 | request_id 重复 | 返回相同结果或明确冲突，不重复创建 |
| DP-WS-005 | 指定 session | pane 创建到显式 session |
| DP-WS-006 | 指定 tab_id | pane 直接创建到目标 Tab并复核归属 |
| DP-WS-007 | new-session 同名资源已存在 | action 前拒绝，不退化为 new-pane |
| DP-WS-008 | action 前创建失败 | request_id 可安全复用；结果未知时保留 unresolved |
| DP-WS-009 | new-tab 创建与视角恢复 | 创建新 Tab 并运行 command；`focus=false` 与有效 `return_tab_id` 时恢复该 session 的目标 Tab |
| DP-WS-010 | 无效 return_tab_id | new-tab 或指定 Tab 的 new-pane 在 action 前返回 `workspace_not_found`，不创建资源 |
| DP-TAB-001 | tab_list | 返回稳定 ID、活动状态来源和 pane 归属 |
| DP-TAB-002 | workspace_create new-tab | 返回新 `tab_id` 与结构化 Tab 信息 |
| DP-TAB-003 | tab_focus | 可观察时确认目标活动状态 |
| DP-TAB-004 | tab_rename | 按稳定 ID 修改并确认名称 |
| DP-TAB-005 | tab_close 无 force | 返回 `permission_denied` |
| DP-TAB-006 | tab_close 受保护 Tab | 返回 `permission_denied`，资源保持存在 |
| DP-TAB-007 | tab_close 正常目标 | 确认 Tab 或 session 状态并返回 resources |

## Pane I/O 与关闭

| ID | 场景 | 预期 |
|----|------|------|
| DP-PANE-001 | pane_write_text 写入 | 调用目标 pane 的 `write-chars` |
| DP-PANE-002 | pane_send_key 写入 | 公共 key 映射为单个 zellij `send-keys` 参数 |
| DP-PANE-003 | plugin pane 写入 | 返回 `permission_denied` |
| DP-PANE-004 | viewport screen | `full=false` 返回 viewport |
| DP-PANE-005 | full screen | `full=true` 返回 full scrollback |
| DP-PANE-006 | ANSI 开关 | true 保留，false 清理 escape |
| DP-PANE-007 | 超长 screen | 保留末尾 262144 字符并设置 `truncated=true` |
| DP-PANE-008 | pane_close 无 force | 返回 `permission_denied` |
| DP-PANE-009 | plugin pane 或当前 MCP pane关闭 | 返回 `permission_denied` |
| DP-PANE-010 | pane_close 正常目标 | 关闭后重新发现并确认结果 |
| DP-PANE-011 | 关闭后状态未知 | 返回 `internal_error` |
| DP-PANE-012 | 当前 MCP 身份不完整或失效 | pane_close 与 tab_close 均 fail-closed |
| DP-PANE-013 | 最后一个 terminal pane | 只关闭 pane，不主动删除 plugin-only session |

## 资源清理

真实 zellij 场景使用唯一 session、Tab 名称和 pane 标题。场景结束后调用 list tools 确认测试资源状态，并记录受保护目标拒绝结果。

## 执行约束

- 单元测试使用隔离 HOME 和临时目录。
- 真实 zellij 与 Host 场景显式执行。
- 真实 lifecycle 使用独立 HOME、XDG 目录和短路径 `ZELLIJ_SOCKET_DIR`。
- lifecycle 通过已安装 wheel 启动 MCP，不从源码目录导入 runtime。
- 结果报告区分已执行、未执行和环境阻塞。
