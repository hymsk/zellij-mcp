# SPEC 需求覆盖矩阵

[中文](requirements-coverage.cn.md) | [English](requirements-coverage.md)

本文对应根 [SPEC.md](../../SPEC.md) 的全部需求：24 项 direct pane、5 项 HTTP/HTTPS 和 3 项公开接口要求。保留原 `ZMCP-MVP-*` ID，覆盖位置不等价于每个环境都已运行或通过验收。

| ID | 需求摘要 | 覆盖证据 |
|----|----------|----------|
| ZMCP-MVP-001 | 11 个公开 tools | tool catalog 顺序约束、tools/list 单元与 stdio 场景 |
| ZMCP-MVP-002 | MCP stdio 协议 | server protocol 单元与 stdio 子进程 `server_smoke.py` |
| ZMCP-MVP-003 | 只调用 zellij | 静态质量约束与 driver 命令检查 |
| ZMCP-MVP-004 | doctor 检查依赖 | diagnostics、driver capability 和 CLI 测试 |
| ZMCP-MVP-005 | 严格 schema | server 参数校验单元测试 |
| ZMCP-MVP-006 | 结构化 argv | tool schema、driver command 与 KDL 转义测试 |
| ZMCP-MVP-007 | 四种 workspace 模式 | workspace handler、`new-tab` 焦点恢复/创建前拒绝测试与创建集成场景 |
| ZMCP-MVP-008 | 直接运行 command | `zellij_create_pane.py` 与 pane 生命周期场景 |
| ZMCP-MVP-009 | 实时发现 session/pane | workspace list 单元与真实 zellij 场景 |
| ZMCP-MVP-010 | terminal/plugin 分离 | pane 规范化与计数测试 |
| ZMCP-MVP-011 | 稳定 tab_id | Tab handler、driver 与 Tab 生命周期场景 |
| ZMCP-MVP-012 | 指定 Tab 直接路由 | handler 归属复核、`new-pane --tab-id` driver 单元与集成场景 |
| ZMCP-MVP-013 | workspace_create new-tab 参数与结果 | Tab 创建、焦点和 command 测试 |
| ZMCP-MVP-014 | 精确资源定位 | session_name required schema 与跨 session 防误操作测试 |
| ZMCP-MVP-015 | 单用途输入 | split tool required/unknown-field 测试 |
| ZMCP-MVP-016 | 固定 key 枚举 | pane_send_key catalog 与非法 key 测试 |
| ZMCP-MVP-017 | viewport/full | pane_screen 参数映射测试 |
| ZMCP-MVP-018 | ANSI 选项 | ANSI 保留与清理测试 |
| ZMCP-MVP-019 | 262144 字符上限 | screen 字符、UTF-8 响应字节与 bounded dump 测试 |
| ZMCP-MVP-020 | force=true | pane_close 与 tab_close 拒绝测试 |
| ZMCP-MVP-021 | pane 特殊目标保护 | pane safety 单元与集成场景 |
| ZMCP-MVP-022 | Tab 特殊目标保护 | Tab close 安全测试 |
| ZMCP-MVP-023 | 关闭结果确认和范围 | pane/Tab/session 三态、action 后发现失败及不主动删除 session 测试 |
| ZMCP-MVP-024 | MCP Host 统一验收 | stdio server smoke 与 Host discovery/I-O 手工验收步骤 |

## 传输与公开接口

| ID | 需求摘要 | 覆盖证据 |
|----|----------|----------|
| ZMCP-HTTP-001 | HTTP 协议与版本协商 | [HTTP 单元测试](../../tests/unit/test_http_transport.py)：真实 loopback initialize/initialized/list/call、版本协商、请求方法和 session headers |
| ZMCP-HTTP-002 | 认证与访问白名单 | [HTTP 单元测试](../../tests/unit/test_http_transport.py)：Bearer、Host/Origin、重复安全 header、wildcard listener 白名单 |
| ZMCP-HTTP-003 | session 与资源有界 | [HTTP 单元测试](../../tests/unit/test_http_transport.py)：request_id 隔离、TTL/容量、并发 DELETE、连接上限、超时和响应限制；模拟工具验证，不操作真实 zellij |
| ZMCP-HTTP-004 | 原生 HTTPS | [HTTP 单元测试](../../tests/unit/test_http_transport.py)：`test_native_https_handshake_bearer_auth_and_safe_tls_errors` 使用临时证书验证 TLS、认证与配置错误 |
| ZMCP-HTTP-005 | CLI 显式启用 HTTP | [HTTP 单元测试](../../tests/unit/test_http_transport.py)：默认 stdio、环境 token、listener/allowlist/TLS 配置校验、明文非 loopback 警告 |
| ZMCP-API-001 | 机器可读调用指导 | [质量约束](../../tests/unit/test_quality_constraints.py)、[源码 smoke](../../tests/integration/server_smoke.py) 和 [安装后 smoke](../../tests/integration/installed_wheel_smoke.py)：annotations、参数说明、实际默认值及 initialize 指引 |
| ZMCP-API-002 | 创建请求去重 | [server 单元测试](../../tests/unit/test_mcp_server.py)：request_id 重放/冲突、缓存容量、失败释放与未知结果保护；[driver 单元测试](../../tests/unit/test_zellij_driver.py)：失败回滚的未知结果 |
| ZMCP-API-003 | 安装来源可追溯 | [质量约束](../../tests/unit/test_quality_constraints.py) 的版本字面量、wheel/metadata 与英文 README 长描述验证；[安装后 smoke](../../tests/integration/installed_wheel_smoke.py) 的版本来源和包说明校验 |

## 质量约束

- SPEC 与本文的全部 `ZMCP-*` ID 集合必须完全一致。
- 每份文档中的 ID 不得重复。
- 原 24 个 MVP ID 保持稳定；新增需求必须同步覆盖证据。
- tool catalog 名称及顺序与 SPEC、双语 README 和接口参考必须一致。

这些一致性约束由 `tests/unit/test_quality_constraints.py` 校验。真实 Host 和跨机器网络需在目标环境单独验收，不能以模拟工具或 loopback 测试替代。
