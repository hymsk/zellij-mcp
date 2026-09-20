# Project Layout

[中文](project-layout.cn.md) | [English](project-layout.md)

Paths are relative to the repository root:

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
│   ├── integration/       # Explicit real zellij probes
│   └── unit/              # Unit tests collected by default pytest
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

Python caches, pytest caches, build directories, coverage files, and virtual environments are generated artifacts and are not part of the project layout.

English is the default: human-facing documents use ordinary `*.md` files, paired with `*.cn.md` Chinese translations. The sole exception is `SPEC.md`, the single Chinese-only specification referenced by both languages. There are no symlinks or duplicate language aliases. Other body links stay in the selected language; the language switch links the matching edition. Package metadata reads the English `README.md` directly.

## Module responsibilities

| Module | Responsibility |
|--------|----------------|
| `SPEC.md` | Single Chinese-only specification for current requirements, public behavior, and acceptance criteria |
| `README.md` / `README.cn.md` | Matching English and Chinese overviews and quick starts; `README.md` is the default entry and package long description |
| `zellij_mcp/cli.py` | Explicit CLI dispatch and stdio/HTTP listener configuration |
| `zellij_mcp/diagnostics.py` | Python and zellij runtime diagnostics |
| `zellij_mcp/provenance.py` | Read the source commit and dirty state embedded in wheels |
| `zellij_mcp/host_context.py` | Recover validated zellij Host context |
| `zellij_mcp/core/types.py` | Workspace references and shared base types |
| `zellij_mcp/drivers/command.py` | Sole zellij subprocess boundary |
| `zellij_mcp/drivers/discovery.py` | Pure parsing and normalization of session, Tab, and pane output |
| `zellij_mcp/drivers/zellij.py` | zellij action facade, lifecycle verification, and rollback semantics |
| `zellij_mcp/server/tool_catalog.py` | Names, descriptions, input schemas, and annotations for 11 tools |
| `zellij_mcp/server/tool_runtime.py` | Argument validation, dispatch, request cache, and handlers |
| `zellij_mcp/server/protocol.py` | stdio JSON-RPC, MCP methods, and bounded responses |
| `zellij_mcp/server/http_transport.py` | Streamable HTTP sessions, authentication, allowlists, and native HTTPS |
| `zellij_mcp/server/main.py` | Public facade assembling protocol and tool runtime |
| `scripts/check_docs.py` | Document links, language consistency, and section checks |
| `tests/unit/` | Repeatable protocol, schema, context recovery, and driver tests |
| `tests/integration/` | Explicitly run real zellij MCP probes |

## Dependency direction

```text
cli -> diagnostics / server facade
server facade -> protocol / tool runtime
tool runtime -> core / drivers
driver facade -> command / discovery
command -> zellij executable
```

`tool_catalog.py` is the sole runtime source for the public contract. At startup, `ToolRuntime` asserts that handlers exactly match the catalog. `protocol.py` does not know about zellij, `command.py` does not parse domain objects, and `discovery.py` does not execute subprocesses.
