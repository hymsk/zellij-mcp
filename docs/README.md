# Zellij MCP Documentation

[中文](README.cn.md) | [English](README.md)

Start with the [project README](../README.md) to install the server and connect your MCP Host. Use the guides below when you need a deployment example, a tool parameter, or a development check.

## Find what you need

| I want to… | Read |
| --- | --- |
| Install zellij and configure a local or remote Host | [Installation](guides/installation.md) |
| Run on Windows through WSL2 | [Windows/WSL2](guides/windows.md) |
| Create a terminal, send input, and collect results | [Interactive usage](guides/interactive.md) |
| Look up tool parameters, results, and errors | [Tool reference](reference/mcp-tools.md) |
| Understand supported behavior and limitations | [Specification](../SPEC.md) |
| Contribute or run the checks | [Contributing](../CONTRIBUTING.md) and [Testing](testing/README.md) |

## Documentation sections

| Section | Contents |
| --- | --- |
| [architecture/README.md](architecture/README.md) | Direct pane architecture and component boundaries |
| [decisions/README.md](decisions/README.md) | Key architecture decisions |
| [design/README.md](design/README.md) | Direct pane interaction boundaries |
| [guides/README.md](guides/README.md) | Installation, operation, and manual checks |
| [reference/README.md](reference/README.md) | Features, tool contracts, and project layout |
| [requirements/README.md](requirements/README.md) | Specification entry point and legacy MVP links |
| [testing/README.md](testing/README.md) | Test plans, cases, and requirement coverage |

## Maintenance

English `*.md` files are the default; `*.cn.md` files contain Chinese translations. Both are regular files. The sole exception is [SPEC.md](../SPEC.md): it is maintained only in Chinese as the single behavior and acceptance baseline, shared by both languages. Keep other documents' translations, references, and tests aligned when it changes; see [Contributing](../CONTRIBUTING.md).
