# Zellij MCP 规格

本规范仅维护中文版本，是项目唯一的需求、公开行为和验收基线。

## 1. 文档职责与兼容基线

本文是 `zellij-mcp` 当前需求、公开行为和验收标准的统一规范，只记录已经实现的能力。需求变更先更新本文，再同步实现、接口参考和测试；未实现的方案不能写成当前承诺。

- [README](README.cn.md) 提供项目概览和快速开始，中英文版本同步维护。
- [docs/](docs/README.cn.md) 提供安装指南、详细参数、架构解释、ADR 和测试证据，不另立需求基线。
- [tool_catalog.py](zellij_mcp/server/tool_catalog.py) 是公开 tool schema 的唯一运行时来源；本文、接口参考和实际 `tools/list` 必须一致。发现差异时应核实并修正，不以文档推断尚未实现的能力。
- `v1.0.0rc1` 是当前公开兼容基线；从该 tag 起维护 MCP tool、CLI 和配置行为的向后兼容。行为变更须在本文说明兼容性影响。本次版本调整不改变现有 MCP tool、CLI 或配置行为。

## 2. 目标与范围

将 zellij 的 session、Tab 和 terminal pane 通过 MCP 暴露给受信任的 Host，使调用方能够发现资源、直接运行命令、输入、读屏和关闭资源。

- 支持 Linux，Python 运行时兼容目标为 3.7+，运行时不依赖第三方 Python 包。
- Windows 部署按 WSL2 的 Linux 环境组织；Windows Host 可通过 `wsl.exe` 启动本机 stdio 服务，对外监听由 WSL 和 Windows 网络配置共同完成。原生 Windows 运行时不在当前基线内，WSL/Host/网络组合需在目标环境验收，步骤见 [Windows 指南](docs/guides/windows.cn.md)。
- 只支持 zellij；由用户独立安装，不提供 tmux/screen 兼容层。
- 默认使用 stdio；显式启用 Streamable HTTP，可配置原生 HTTPS。
- 通过 `doctor` 检查后台 session 创建、稳定 Tab 操作和 direct pane I/O 能力，不仅根据 zellij 版本号推断可用性。
- Host 配置路径、注册器及外部组件管理器不属于本源码仓库接口。
- 不提供 OAuth、多租户授权隔离、任务完成检测、后台自动清理或人机输入锁；当前不提供 MCP resources、prompts 或 tool `outputSchema`。

## 3. 资源模型与发现

- session 使用 `session_name` 标识。Tab 使用 session 内稳定的非负整数 `tab_id`，不是显示位置。
- pane ID 规范化为 `terminal_N` 或 `plugin_N`；两类 ID 独立，不能相互替代。
- 精确 pane I/O、pane 关闭和 Tab focus/rename/close 必须显式提供 `session_name` 与对应 ID，不能猜测目标。连接多个 MCP server 时，调用方还必须保留 server 身份。
- list 与创建目标解析可使用当前或唯一活动 session。存在多个候选且无明确目标时须要求指定 session；list 可选择 `all_sessions=true`。
- `workspace_list` 的 `pane_count` 与 `terminal_pane_count` 统计 terminal pane，`plugin_pane_count` 单列，`total_pane_count` 包含两者。`include_plugins=false` 只省略 plugin 明细，不省略计数。
- `workspace_list.session_name` 优先于 `all_sessions`；`tab_list` 禁止同时提供这两个参数。`tab_list.include_panes` 默认 true。
- 枚举失败不得伪装为空集合。调用方须检查错误以及 `degraded`、`failed_sessions`，再判断发现结果是否完整。

## 4. MCP 接口契约

公开 tool 集合及顺序固定如下。完整字段、返回结构和 key 枚举见 [MCP Tools 参考](docs/reference/mcp-tools.cn.md)。

| Tool | 必填参数 | 行为与关键约束 |
|------|----------|----------------|
| `zellij_mcp_doctor` | 无 | 检查 Python、zellij、action 能力及服务端 zellij 上下文 |
| `workspace_create` | `request_id`、`command` | 创建 pane、Tab 或 session，直接运行 argv |
| `workspace_list` | 无 | 发现 live session/pane，分别返回 terminal/plugin 计数 |
| `tab_list` | 无 | 返回稳定 Tab ID、活动状态及 pane 归属 |
| `tab_focus` | `session_name`、`tab_id` | 聚焦目标 Tab，返回验证与降级信息 |
| `tab_rename` | `session_name`、`tab_id`、`tab_name` | 按稳定 ID 重命名并复核 |
| `tab_close` | `session_name`、`tab_id` | 关闭整个 Tab；执行须 `force=true` |
| `pane_write_text` | `session_name`、`pane_id`、`text` | 写字面文本，不自动追加 Enter |
| `pane_send_key` | `session_name`、`pane_id`、`key` | 发送一个固定枚举键 |
| `pane_screen` | `session_name`、`pane_id` | 读取 viewport 或 full scrollback，可保留 ANSI |
| `pane_close` | `session_name`、`pane_id` | 关闭一个 terminal pane；执行须 `force=true` |

### 4.1 参数与结果

- tool arguments 必须是 object；未知字段、缺失 required、错误类型、非法枚举、NUL、超限值和非法参数组合须在 action 前拒绝。
- identifier 最长 256 字符，`cwd` 最长 4096 字符，Tab ID 范围为 0–2147483647。
- `command` 为非空字符串数组，最多 256 项，每项最长 65536 字符，总 UTF-8 大小最多 512 KiB。服务端不拼接 shell 字符串；管道和重定向需要调用方显式运行 shell。
- `environment` 是字符串 map，最多 256 项，总 UTF-8 大小最多 65536 bytes；键须匹配 `[A-Za-z_][A-Za-z0-9_]*`，以 argv 形式的 `env` 应用到命令。
- `pane_write_text.text` 最多 65536 字符且最多 65536 UTF-8 bytes。
- `tools/call` 同时以 JSON text content 和 `structuredContent` 表达结果；工具失败设置 `isError=true`，payload 包含平铺的 `error=true`、`code`、`message`，并可包含 `details`。
- 业务错误码为 `invalid_argument`、`zellij_not_available`、`workspace_not_found`、`permission_denied`、`internal_error`。协议层解析、请求和方法错误使用 JSON-RPC 错误响应。

### 4.2 调用方指导与 annotations

`initialize.instructions` 仅提供简短的选择条件与共用约束：用户明确要求 zellij，或需要持久交互终端、后台终端任务、已配置远程服务的终端访问时使用；其余场景优先使用 Host 常规执行工具。操作已有资源前先发现，保护用户焦点与无关工作。`workspace_create` 描述也包含持久交互与后台终端任务用途，以兼顾未传递初始化指导的 Host。详细焦点、完成判断和清理指导由相关 tool 描述提供，不在初始化指导中重复展开；这不是工具按需加载，`tools/list` 仍返回完整工具集合。所有顶层参数都有说明，boolean 与创建模式声明实际默认值。Host 是否把这些字段交给模型由 Host 决定，README 不会自动进入模型上下文。

工具描述聚焦用途与就地风险提醒，参数描述聚焦 schema 无法表达的语义与组合约束，避免重复类型、长度及默认值。精简不得移除发现后操作、焦点保护、输入送达不等于完成、核实完成后的最小范围清理、保留例外及创建重试边界。质量测试限制工具与顶层参数描述合计不超过 5200 字符（不含初始化指导）；字符预算不是 token 数，也不改变完整工具集合和参数契约。

全部 tools 显式提供 `readOnlyHint`、`destructiveHint`、`idempotentHint`、`openWorldHint`。doctor、两种 list 和 screen 是只读且幂等的 closed-world tools；focus/rename 是非破坏、幂等的 closed-world mutations；创建、输入和关闭标记 destructive/open-world，且不声明跨进程幂等。这些 hints 不替代参数校验和运行时保护。

## 5. 创建、交互与生命周期

### 5.1 创建与重试

- `workspace_type` 默认 `auto`：处于 zellij 内或提供 `session_name` 时选择 `new-tab`，否则创建后台 `new-session`。
- `new-pane` 在已有 session 创建 pane，可通过 `tab_id` 直接路由到指定 Tab；指定 `tab_id` 必须同时提供 `session_name`，创建后复核归属。
- `new-tab` 在已有 session 创建 Tab，可设置 `tab_name`；返回 `tab_id`，不返回 `pane_id`，调用方随后用 `tab_list` 发现 pane。
- `new-session` 创建后台 session；显式同名 session 已存在时拒绝，不能降级为向其添加 pane。
- `cwd` 可选，省略时取运行时/zellij 上下文，不承诺采用 Host 项目目录。`environment` 仅向新命令添加或覆盖环境。
- `request_id` 仅对创建去重。同一 ID、相同参数返回已有结果；同一 ID、不同参数拒绝。每个工具运行时缓存最多 1024 条，满后拒绝新 ID，不驱逐旧结果。
- 缓存作用域为当前 stdio 进程或当前 HTTP MCP session，不跨 session、过期或重启。可确认未发生 mutation 的失败释放 ID；结果未知的创建保留 unresolved 状态，不能通过换 ID 盲目重放。

### 5.2 焦点与输入

- 创建默认 `focus=false`；新 Tab 使用 no-focus，指定 Tab 创建 pane 时尝试保持原焦点。调用方检查 `focus_verified`、`focus_conflict`、`degraded`，不能把 action 成功等同于焦点验证成功。
- `return_tab_id` 是同 session 的显式恢复目标，要求 `focus=false`；用于 `new-pane` 时还必须提供 `tab_id`。无效恢复目标必须在创建前拒绝。
- 发现、读屏和输入无需先聚焦。仅用户要求或确需用户关注时主动聚焦并说明原因；不要机械恢复旧焦点而覆盖用户并发切换。
- `pane_write_text` 使用 `write-chars`；内嵌换行仍可能提交输入。`pane_send_key` 使用受限 `send-keys`，一次一个枚举键。Ctrl-C、Ctrl-D、Escape 分别映射为单个参数 `Ctrl c`、`Ctrl d`、`Esc`。
- 输入成功只证明 action 被接受，返回 `completion_verified=false`。人工与 MCP 输入按实际到达顺序作用于程序，没有服务端输入锁。

### 5.3 读屏与关闭

- `pane_screen` 使用 `dump-screen`；`full=false` 默认读取 viewport，`full=true` 请求可导出的 full scrollback；`ansi=false` 默认清理 ANSI。
- screen 最多返回 262144 个字符，并继续受 MCP 响应字节上限约束；超限保留末尾内容并设 `truncated=true`，`source=zellij_dump_screen`。full 不代表无限输出。
- plugin pane 不进入 terminal pane 写入、读屏或关闭路径。
- `pane_close` 与 `tab_close` 的 `force` 默认 false，只有 true 才能执行；不得绕过当前 MCP pane 及包含它的 Tab 的保护。
- server 处于 zellij 内但当前 pane 身份不完整、失效或无法验证时，关闭须保守拒绝。HTTP 使用服务端启动上下文，不使用客户端本地上下文。
- 关闭后重新发现并确认 pane、Tab 或 session 状态；无法确认时返回错误。`pane_close` 不主动删除只剩 plugin pane 的 session；zellij 自行结束 session 时以 `session_closed` 报告。
- 调用方确认任务退出或完成且用户未要求保留后，先保存结果、刷新状态，再关闭最小安全范围；关闭整个 Tab 前检查全部 pane。安静屏幕和输入被接受都不是完成证据，不得据此误关无关或仍在运行的工作。

## 6. 传输与安全

### 6.1 stdio

`zellij-mcp serve` 默认启动 newline-delimited JSON-RPC。stdout 仅承载协议消息，诊断使用单独的 CLI 子命令。

支持 initialize、notifications、ping、tools/list、tools/call；无 id 的通知不返回响应，也不因使用 tool request 的 method 而执行副作用。单行请求上限为 1048576 个字符，响应上限为 1 MiB；错误请求有界拒绝后可继续处理后续请求。

### 6.2 Streamable HTTP 与 HTTPS

- 显式使用 `serve --transport streamable-http`；默认 bind 为 `127.0.0.1:8765`。`--host` 接受 IPv4/IPv6 literal，不接受 hostname；wildcard bind 不放宽访问白名单。
- `POST /mcp` 接收单个 UTF-8 JSON-RPC 对象，要求 `Content-Type: application/json`，`Accept` 同时接受 `application/json` 与 `text/event-stream`。请求返回 JSON，接受的通知和客户端响应返回 `202` 空体。`GET /mcp` 返回 `405`，不提供 SSE 流或旧版 HTTP+SSE 端点。
- 协商版本为 `2025-03-26`、`2025-06-18`、`2025-11-25`。初始化后发送 `notifications/initialized`，后续请求携带协商的 `MCP-Protocol-Version` 和返回的 `MCP-Session-Id`。
- `DELETE /mcp` 结束 MCP session，不关闭 zellij 资源。session 空闲过期或服务重启后须重新初始化；创建缓存不随之恢复。
- 上限为 64 个 MCP session、30 分钟空闲 TTL、16 个并发连接；请求和响应各最多 1 MiB，socket 读取超时 5 秒。每次响应关闭 HTTP 连接，通过 session header 延续逻辑会话。
- 必须由 `ZELLIJ_MCP_HTTP_TOKEN` 配置 Bearer token，长度为 32–512 个 ASCII Bearer 字符；真实值不进入仓库、文档或日志。
- 非 loopback listener 必须提供 `--allowed-host`。Host 带端口时精确匹配该端口，不带端口时匹配实际 bind port；`--allowed-origin` 按 scheme、host、有效端口精确匹配。无 Origin 的客户端无需 Origin 白名单；携带 Origin 时必须通过检查。
- loopback 且未配置任何 allowlist 时，只接受实际 listener 的 Host/port，以及相同 scheme/host/port 的 Origin。仅配置 `--allowed-origin` 时，Host 仍默认取 listener IP/port；配置 `--allowed-host` 时按该列表检查 Host。显式配置任一 allowlist 后，自动同源 Origin 放行关闭，携带 Origin 的请求必须匹配显式 `--allowed-origin` 列表。
- `--tls-cert` 与 `--tls-key` 必须成对提供 PEM 文件，原生 HTTPS 最低 TLS 1.2，仍需 Bearer token。非 loopback 明文 HTTP 会向 stderr 警告，部署仅适合受信任网络；远程访问推荐 HTTPS 或安全隧道。

服务以启动它的操作系统用户权限访问 zellij。创建可执行任意调用方 argv，输入可控制终端程序；认证 token 不构成客户端间的资源隔离。只向受信任 Host 提供访问，凭据注入、证书和网络配置由部署者负责。详细配置见 [安装与 Host 集成](docs/guides/installation.cn.md)。

## 7. CLI、安装与可追溯性

- CLI 提供 `serve`、`doctor [--json]`、`version [--json]`；源码目录可使用等价的 `python3 -m zellij_mcp`。
- `doctor` 报告能力、warnings 和 fixes；Python、zellij 或必需 action 不满足要求时返回非零退出码。
- `doctor` 不验证 Host 配置或独立权限策略；其 `capabilities.host` 为 `not_checked`，不能把环境诊断成功当成 Host 集成已验收。
- 安装流程先在 MCP 服务所在机器安装 zellij 并配置服务进程的 `PATH`，再安装 MCP 运行时包，运行 `doctor` 通过后连接 Host。zellij 的下载、校验与安装命令见[安装指南](docs/guides/installation.cn.md#安装-zellij)。
- 通过 `python3 -m pip install .` 安装，开发依赖通过 `python3 -m pip install -e ".[dev]"` 安装。zellij 由用户按流程单独安装，Python 包安装命令不代装 zellij，也不修改 Host 配置。
- 构建时以 Python 3.7+ 可用的字面量解析方式读取版本，不执行包初始化代码。普通 wheel、editable wheel 和预生成元数据均以普通文件 `README.md` 的 UTF-8 英文正文作为 Markdown 长描述，不使用软链接或重复入口。
- wheel 内嵌 `source_commit` 与 `source_dirty`，可由 version/doctor JSON 查询；dirty 只统计已跟踪文件。无可用构建来源时不得伪造 commit。

## 8. 需求与验收追踪

原有 24 个 `ZMCP-MVP-*` ID 保持稳定并迁入本文；新增 HTTP 和公开接口要求单独编号。全部 ID 必须唯一，并与 [需求覆盖矩阵](docs/testing/requirements-coverage.cn.md) 完全对应。覆盖矩阵说明验证位置，不表示所有平台、Host 或真实网络均已执行验收。

### 8.1 Direct pane 基线

| ID | 需求 | 可测试验收口径 |
|----|------|----------------|
| ZMCP-MVP-001 | 公开 tool 集合精确为 11 个 | `tools/list` 返回第 4 节名称，顺序稳定且无重复 |
| ZMCP-MVP-002 | MCP stdio 协议可用 | initialize、notification、ping、tools/list、tools/call 与错误响应结构稳定 |
| ZMCP-MVP-003 | 项目只调用 zellij | 运行代码的复用器命令路径仅包含 zellij |
| ZMCP-MVP-004 | doctor 检查外部依赖 | zellij 缺失或 action 不足时报告 warnings、fixes 与 capability |
| ZMCP-MVP-005 | tool 参数采用严格 schema | required、类型、枚举、长度、UTF-8 大小、NUL 与未知字段在 action 前校验 |
| ZMCP-MVP-006 | command 使用结构化 argv | command 为非空字符串数组，不经过 shell 字符串拼接 |
| ZMCP-MVP-007 | 创建支持四种模式 | `auto/new-pane/new-tab/new-session` 选择和结果可验证；无效 `return_tab_id` 在创建前拒绝 |
| ZMCP-MVP-008 | 创建直接运行 command | pane 初始程序与 argv、cwd、environment 一致 |
| ZMCP-MVP-009 | 实时发现 session 与 pane | 返回 session 明细、当前资源、失败 session 和四类 pane 计数 |
| ZMCP-MVP-010 | terminal/plugin 分离 | 两类 pane 独立保留，plugin 计数单独返回 |
| ZMCP-MVP-011 | Tab 使用稳定 tab_id | list、创建、focus、rename、close 均按稳定非负整数 ID 操作 |
| ZMCP-MVP-012 | 指定 Tab 创建直接路由 | pane 创建到 `tab_id` 指定目标并复核归属 |
| ZMCP-MVP-013 | new-tab 支持名称与焦点参数 | command、tab_name、environment、focus、return_tab_id 组合得到结构化结果 |
| ZMCP-MVP-014 | 精确操作显式定位 | pane I/O 和 Tab focus/rename/close 缺少 session_name 时在 action 前拒绝 |
| ZMCP-MVP-015 | 单用途 pane 输入 | write_text 只接受 text，send_key 只接受 key，不混用字段 |
| ZMCP-MVP-016 | key 集合固定 | 仅接受 catalog 声明的 key 枚举 |
| ZMCP-MVP-017 | viewport 与 full | full 开关映射到对应 dump-screen 范围 |
| ZMCP-MVP-018 | ANSI 选项 | ansi=true 保留，false 清理 escape |
| ZMCP-MVP-019 | screen 有界 | 最多 262144 字符，超限设 truncated=true，并满足响应字节上限 |
| ZMCP-MVP-020 | 关闭要求 force=true | force 缺失或 false 时拒绝 |
| ZMCP-MVP-021 | pane 特殊目标保护 | plugin pane 与当前 MCP pane 不能关闭；server 处于 zellij 内且当前身份不完整时保守拒绝 |
| ZMCP-MVP-022 | Tab 特殊目标保护 | 关闭前检查 pane 归属，拒绝包含当前 MCP pane 的 Tab |
| ZMCP-MVP-023 | 关闭确认且不扩大范围 | 关闭后复核资源，未知结果报错；pane_close 不主动删除 session |
| ZMCP-MVP-024 | Host 统一验收 | 每个目标 Host 发现 11 tools，并按 create/write/screen/close 验收 |

### 8.2 传输与公开接口基线

| ID | 需求 | 可测试验收口径 |
|----|------|----------------|
| ZMCP-HTTP-001 | HTTP 协议与版本协商 | 真实 loopback socket 验证 initialize、initialized、list/call、headers、POST/GET/DELETE 语义 |
| ZMCP-HTTP-002 | 认证与访问白名单 | 缺失/非法 token、Host、Origin 拒绝；wildcard bind 不放宽白名单 |
| ZMCP-HTTP-003 | session 与资源有界 | 验证缓存隔离、TTL、容量、并发、超时和请求/响应大小限制；删除 session 不关闭 zellij |
| ZMCP-HTTP-004 | 原生 HTTPS | TLS 1.2+ 握手、Bearer 认证和 certificate/key 错误路径可验证 |
| ZMCP-HTTP-005 | CLI 显式启用 HTTP | stdio 默认不变；token 必需，非 loopback 明文 listener 警告，TLS 参数必须成对 |
| ZMCP-API-001 | 机器可读调用指导 | 源码及安装后 tools/list 的 annotations、参数说明和默认值完整；initialize 包含焦点及清理指导 |
| ZMCP-API-002 | 创建请求去重 | 验证同 ID 重放、冲突、缓存容量、unresolved 状态，不承诺跨 runtime 去重 |
| ZMCP-API-003 | 安装来源可追溯 | wheel 的 version/doctor 能查询构建来源，源码 commit 与已跟踪文件 dirty 状态符合构建输入 |

## 9. 维护与验证

1. 行为或边界变化先修订本文与对应需求 ID，再同步实现和 [覆盖矩阵](docs/testing/requirements-coverage.cn.md)。不重复利用旧 ID 表示另一项需求。
2. 参数、返回结构或 tool 集合变化时同步 [接口参考](docs/reference/mcp-tools.cn.md)、[功能说明](docs/reference/features.cn.md) 和双语 README；架构决策同步架构文档及 ADR。
3. 文档至少运行 `python3 scripts/check_docs.py`、`python3 -m pytest tests/unit/test_quality_constraints.py -q` 和 `git diff --check -- .`，校验链接、工具名称与需求追踪。
4. Python 修改运行 compileall；行为修改运行单元测试与相关集成验证。完整命令和副作用见 [测试文档](docs/testing/README.cn.md)。

项目不配置 GitHub Actions CI，本地检查仍是交付要求：

```bash
make check
make verify
make integration-smoke
make integration-installed
```

真实 zellij 生命周期测试须显式执行 `make integration-isolated`，会在独立 HOME、XDG 和 socket 目录创建并清理资源。真实 Host、跨机器网络、特定 Python/zellij 版本验证须分别记录已执行、未执行或环境阻塞；单元测试通过不等价于这些场景已验收。
