# 项目目录

[中文](project-layout.cn.md) | [English](project-layout.md)

以下结构以仓库根目录为起点：

```text
.
├── AGENTS.md
├── CONTRIBUTING.md
├── CONTRIBUTING.cn.md
├── LICENSE
├── Makefile
├── README.md
├── README.cn.md
├── SECURITY.md
├── SECURITY.cn.md
├── SPEC.md
├── pyproject.toml
├── docs/
├── scripts/check_docs.py
├── tests/
│   ├── integration/       # 显式运行的真实 zellij 探针
│   └── unit/              # 默认 pytest 收集的单元测试
└── zellij_mcp/
    ├── cli.py
    ├── provenance.py
    ├── diagnostics.py
    ├── host_context.py
    ├── core/
    ├── drivers/
    │   ├── command.py
    │   ├── discovery.py
    │   └── zellij.py
    └── server/
        ├── main.py
        ├── http_transport.py
        ├── protocol.py
        ├── tool_catalog.py
        └── tool_runtime.py
```

Python cache、pytest cache、构建目录、coverage 文件和虚拟环境属于生成物，不计入项目结构。

默认使用英文：面向人的文档以普通 `*.md` 文件保存英文正文，`*.cn.md` 保存对应中文翻译。唯一例外是 `SPEC.md`，仅维护中文规范，由两种语言共同引用。不使用软链接或重复语言别名；其他正文链接保持当前语言，语言切换入口链接对应版本。包元数据直接读取英文 `README.md`。

## 模块职责

| 模块 | 职责 |
|------|------|
| `SPEC.md` | 仅维护中文的唯一规范，统一管理需求、公开行为和验收标准 |
| `README.md` / `README.cn.md` | 内容对应的英文和中文概览与快速开始；`README.md` 是默认入口和包长描述来源 |
| `zellij_mcp/cli.py` | 显式 CLI 分派与 stdio/HTTP listener 配置入口 |
| `zellij_mcp/diagnostics.py` | Python 与 zellij 运行时诊断 |
| `zellij_mcp/provenance.py` | 读取 wheel 内嵌的源码 commit 与 dirty 状态 |
| `zellij_mcp/host_context.py` | 恢复经过校验的 zellij Host 上下文 |
| `zellij_mcp/core/types.py` | workspace 引用与公共基础类型 |
| `zellij_mcp/drivers/command.py` | 唯一 zellij subprocess 边界 |
| `zellij_mcp/drivers/discovery.py` | session、Tab 与 pane 输出的纯解析和规范化 |
| `zellij_mcp/drivers/zellij.py` | zellij action facade、生命周期确认与回滚语义 |
| `zellij_mcp/server/tool_catalog.py` | 11 个 tool 名称、描述、input schema 与 annotations |
| `zellij_mcp/server/tool_runtime.py` | 参数校验、dispatch、request cache 与 handlers |
| `zellij_mcp/server/protocol.py` | stdio JSON-RPC、MCP 方法和有界响应 |
| `zellij_mcp/server/http_transport.py` | Streamable HTTP 会话、认证、访问白名单与原生 HTTPS |
| `zellij_mcp/server/main.py` | 组装 protocol 与 tool runtime 的公共 facade |
| `scripts/check_docs.py` | 文档链接、语言一致性与分区检查 |
| `tests/unit/` | 可重复的协议、schema、上下文恢复和 driver 测试 |
| `tests/integration/` | 显式运行的真实 zellij MCP 探针 |

## 依赖方向

```text
cli -> diagnostics / server facade
server facade -> protocol / tool runtime
tool runtime -> core / drivers
driver facade -> command / discovery
command -> zellij executable
```

`tool_catalog.py` 是公开 contract 的唯一运行时来源；启动时 `ToolRuntime` 断言 handlers 与
catalog 精确一致。`protocol.py` 不了解 zellij，`command.py` 不解析业务对象，
`discovery.py` 不执行 subprocess。
