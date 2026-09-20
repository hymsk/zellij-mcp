# Direct Pane 测试用例

[中文](test-cases.cn.md) | [English](test-cases.md)

## zellij_mcp_doctor

### 可用环境

- 输入：空 object。
- 前置：Python 与 zellij 可用。
- 预期：返回版本、后台创建、稳定 Tab、direct pane I/O、当前上下文与 warning 列表。

### zellij 缺失

- 输入：空 object。
- 前置：PATH 中没有 zellij。
- 预期：`ok=false`，capability 为 false，并给出安装提示。

## workspace_create

### 创建 pane

- 输入：`request_id`、`command=["/bin/sh"]`、`workspace_type="new-pane"`、目标 session。
- 预期：返回实际 `session`、`pane_id`、`tab_id` 和 attach hint。

### 创建 session

- 输入：`workspace_type="new-session"` 与唯一 `session_name`。
- 预期：后台 session 存在，初始 terminal pane 运行指定 command。

### argv 与 environment

- 输入：含空格、引号和 Unicode 的 argv，结构化 environment map。
- 预期：参数按项传递，cwd 与环境值在 pane 内可观察。

### 指定 Tab

- 输入：目标 `tab_id`。
- 预期：新 pane 的 `tab_id` 与目标一致。

### 创建 Tab 与视角恢复

- 输入：`workspace_type="new-tab"`、目标 session、`focus=false` 与已有的 `return_tab_id`。
- 预期：新 Tab 的初始 pane 运行 command，目标 session 的活动 Tab 恢复为 `return_tab_id`。

### 无效视角恢复目标

- 输入：`new-tab` 或指定目标 Tab 的 `new-pane`，以及不存在的 `return_tab_id`。
- 预期：创建前返回 `workspace_not_found`，不执行 zellij 创建 action。

### 非法输入

- 输入：空 command、超长字段、非法 environment、未知字段。
- 预期：返回 `invalid_argument`，无 zellij action。

## workspace_list

### 当前 session

- 前置：3 个 terminal pane 与 1 个 plugin pane。
- 预期：`total_pane_count=4`、`pane_count=3`、`terminal_pane_count=3`、`plugin_pane_count=1`。

### 全部 session

- 输入：`all_sessions=true`。
- 预期：返回活动 session 聚合与每个 session 的 pane 明细。

### 发现失败

- 前置：zellij session 或 pane 枚举命令失败。
- 预期：返回结构化错误，不返回虚假零计数。

## tab_list

### 多 Tab

- 输入：目标 session，`include_panes=true`。
- 预期：返回稳定 `tab_id`、名称、活动状态来源、四类 pane 计数和 pane 归属。

### pane 归属无法确认

- 前置：pane 的 Tab ID 无法映射。
- 预期：返回 `internal_error`。

## workspace_create new-tab

### 创建 shell Tab

- 输入：唯一 `request_id`、`command=["/bin/sh"]`、`workspace_type="new-tab"` 与 `tab_name`。
- 预期：返回新 `tab_id` 和 Tab 信息。

### 创建 command Tab

- 输入：command、cwd、environment。
- 预期：初始 pane 直接运行 command。

### 焦点参数

- 输入：`focus=true` 或 `return_tab_id`。
- 预期：返回 action accepted 与可观察的焦点验证结果。

## tab_focus

- 输入：稳定 `tab_id`。
- 预期：目标 Tab action 成功；活动状态可观察时 `verified=true`。

## tab_rename

- 输入：稳定 `tab_id` 与新名称。
- 预期：按 ID 修改并重新枚举确认名称。

## tab_close

### 缺少 force

- 输入：目标 `tab_id`。
- 预期：`permission_denied`。

### 当前 MCP pane 所在 Tab

- 输入：目标 `tab_id`、`force=true`。
- 预期：`permission_denied`，Tab 保持存在。

### 正常关闭

- 输入：其他 Tab、`force=true`。
- 预期：重新枚举确认 Tab 或 session 状态，返回 `verified=true`。

## pane_write_text

- 输入：`session_name`、`pane_id`、`text`。
- 预期：调用 `write-chars`，返回 `kind="text"` 与 UTF-8 字节数。

### 交叉字段

- 输入：额外提供 `key`。
- 预期：`invalid_argument`，不调用 zellij action。

## pane_send_key

- 输入：`key="Enter"`。
- 预期：调用 `send-keys`，返回 `kind="key"`。

### 交叉字段

- 输入：额外提供 `text`。
- 预期：`invalid_argument`，不调用 zellij action。

## pane_screen

### 可见区域

- 输入：`full=false`、`ansi=false`。
- 预期：返回 viewport 文本，ANSI 已清理。

### 完整回滚与 ANSI

- 输入：`full=true`、`ansi=true`。
- 预期：调用 full dump-screen 并保留 ANSI。

### 截断

- 前置：screen 超过 262144 个字符。
- 预期：保留末尾 262144 个字符，`truncated=true`。

## pane_close

### 缺少 force

- 预期：`permission_denied`。

### plugin pane 与当前 MCP pane

- 输入：`force=true`。
- 预期：`permission_denied`，目标保持存在。

### 正常关闭

- 输入：其他 terminal pane、`force=true`。
- 预期：重新发现资源并返回 `closed=true`、`verified=true`。

### 后置条件未知

- 前置：关闭后 session 或 pane 无法枚举。
- 预期：返回 `internal_error`。
