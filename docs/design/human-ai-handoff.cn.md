# 直接 Pane 交互边界

[中文](human-ai-handoff.cn.md) | [English](human-ai-handoff.md)

## 参与方

- MCP Host 通过 `pane_write_text`、`pane_send_key` 和 `pane_screen` 操作指定 terminal pane。
- 用户通过 zellij 界面观察并操作同一个 terminal pane。
- zellij 负责将输入交给 pane 内程序，并维护终端画面。

## 资源定位

每次调用使用 `session_name + pane_id` 定位目标。调用方在写入前可以使用 `workspace_list` 或 `tab_list` 刷新 pane 的 session、Tab、标题、命令和状态信息。

## MCP 写入

MCP Host 优先使用两个单用途输入接口：

- `pane_write_text.text`：通过 `write-chars` 写入字面文本。
- `pane_send_key.key`：通过 `send-keys` 写入一个固定枚举键。

成功结果表示 zellij 接受该 action。目标程序的响应通过 `pane_screen` 观察。

## 人工输入

用户可以在 zellij pane 中直接输入。MCP Host 与用户共同作用于 pane 内程序时，输入顺序由实际到达 zellij 的顺序决定。

默认保持用户的 Tab 焦点，发现、读屏和直接 pane 输入无需聚焦。仅用户要求或确需用户关注时调用 `tab_focus` 或使用 `focus=true`，并说明原因；不覆盖用户并发切换的焦点。`return_tab_id` 是显式恢复请求，不能机械地把旧焦点快照当成用户当前意图。

## 调用方协调

需要人工确认的流程由调用方明确组织：

1. 调用 `workspace_list` 或 `tab_list` 确认目标。
2. 调用 `pane_screen` 读取当前内容。
3. 向用户展示需要确认的信息。
4. 收到确认后调用 `pane_write_text` 或 `pane_send_key`。
5. 再次调用 `pane_screen` 检查目标程序输出。

涉及高风险命令时，调用方应在写入前核对 session、pane、Tab、标题与命令字段，并将业务审批作为独立前置条件。

## 观测边界

- `pane_screen(full=false)` 表示当前 viewport。
- `pane_screen(full=true)` 表示 zellij 可导出的 full scrollback。
- `ansi=true` 保留 ANSI escape sequence。
- `truncated=true` 表示结果已按 262144 字符上限截断。
- screen 文本由 pane 内程序和终端共同产生，调用方按目标程序协议解释内容。

## 关闭边界

- 关闭操作要求 `force=true`。
- plugin pane 不能作为 terminal pane 关闭。
- 当前 MCP pane 及包含它的 Tab 受保护。
- 调用方在关闭前先发现资源，并处理关闭后的结构化结果。
- 本任务相关 pane/Tab 已确认退出或处理完成且用户未要求保留时，先保存必要结果，再及时刷新状态并关闭最小安全范围；整个 Tab 必须检查全部 pane，保留无关、仍在运行或需保留的工作。
- 不将输入接受或安静屏幕当成完成证据；完成或归属不明时先核实或询问。服务端不自动判定任务完成或清理资源，这些是调用方指导，不新增控制状态机。
