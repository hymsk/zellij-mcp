# Zellij MCP 文档

[中文](README.cn.md) | [English](README.md)

先阅读[项目 README](../README.cn.md)，安装服务并连接 MCP Host。需要部署示例、工具参数或开发检查时，再查阅下列文档。

## 按任务查找

| 我想要…… | 阅读 |
| --- | --- |
| 安装 zellij，配置本机或远程 Host | [安装指南](guides/installation.cn.md) |
| 在 Windows 上通过 WSL2 运行 | [Windows/WSL2](guides/windows.cn.md) |
| 创建终端、发送输入并收集结果 | [交互使用](guides/interactive.cn.md) |
| 查询工具参数、返回值和错误 | [工具参考](reference/mcp-tools.cn.md) |
| 了解支持的行为与限制 | [规范](../SPEC.md) |
| 参与贡献或运行检查 | [贡献指南](../CONTRIBUTING.cn.md)与[测试文档](testing/README.cn.md) |

## 文档分区

| 分区 | 内容 |
|------|------|
| [architecture/README.cn.md](architecture/README.cn.md) | direct pane 总体架构与组件边界 |
| [decisions/README.cn.md](decisions/README.cn.md) | 项目关键决策 |
| [design/README.cn.md](design/README.cn.md) | 直接 pane 交互边界 |
| [guides/README.cn.md](guides/README.cn.md) | 操作与手工检查 |
| [reference/README.cn.md](reference/README.cn.md) | 功能、tool 契约与项目布局 |
| [requirements/README.cn.md](requirements/README.cn.md) | SPEC 需求入口与原 MVP 链接兼容 |
| [testing/README.cn.md](testing/README.cn.md) | 测试计划、用例和覆盖矩阵 |

## 维护规则

默认英文使用 `*.md`，中文翻译使用 `*.cn.md`，两者均为普通文件。唯一例外是 [SPEC.md](../SPEC.md)：仅维护中文，作为统一的行为和验收基线，由两种语言共同引用。变更时保持其他文档的翻译、参考和测试一致，详见[贡献指南](../CONTRIBUTING.cn.md)。
