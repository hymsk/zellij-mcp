# 贡献指南

[中文](CONTRIBUTING.cn.md) | [English](CONTRIBUTING.md)

## 开发

开发前先阅读 [SPEC.md](SPEC.md)，以其中的需求、公开行为和验收标准为准。规范仅维护这一份中文文件，行为变更时先更新规范和需求覆盖矩阵，再同步实现及详细参考文档。其他面向人的文档保持中英文内容一致，英文默认使用普通 `*.md` 文件，中文翻译使用 `*.cn.md`，不使用软链接或重复别名。除共同引用 `SPEC.md` 外，正文链接保持同一语言。

首次准备环境时，先按[安装指南](docs/guides/installation.cn.md#安装-zellij)安装 zellij 并配置 `PATH`，再安装开发依赖。运行真实 zellij 集成测试前，先执行 `python3 -m zellij_mcp doctor --json` 确认所需能力可用。

```bash
python3 -m pip install -e ".[dev]"
make check
make verify
python3 tests/integration/server_smoke.py
python3 tests/integration/installed_wheel_smoke.py
python3 tests/integration/zellij_isolated_lifecycle.py
```

本项目不配置 GitHub Actions CI，请在本地运行相关检查。真实 zellij 生命周期测试会创建并关闭 session、Tab 和 pane，必须显式执行。测试命令与副作用见[测试文档](docs/testing/README.cn.md)。

## Git 提交

使用 Conventional Commits：`<type>[(scope)][!]: <summary>`。常用类型包括 `feat`、`fix`、`refactor`、`docs`、`test`、`build`、`ci` 和 `chore`。每个提交聚焦一个逻辑目的；标题简洁且有实质含义，不能只写版本号或空泛的更新描述。

- 首次公开提交、初始导入和历史压缩后的公开基线提交必须有实质正文。版本发布、公开行为或兼容性变化、复杂修复和大型重构必须解释标题无法表达的背景和影响；简单、明确的局部修正无需堆砌模板。
- 说明目的、主要能力或变化、相关模块、兼容性与安全边界，以及关键取舍。文件列表或一句 `initial release` 不足以解释变更。破坏性变更使用 `!` 并说明迁移要求。
- 记录实际执行的相关检查和结果，包括未运行、失败和环境限制。存在测试文件不代表测试通过；不得编造验证结论或审查 trailer。
- 提交前审阅完整 diff 和完整消息；提交后通过 `git log -1 --format=full` 确认正文已保存。历史中的简略提交不能豁免这些要求，squash 也不免除实质正文要求。
- AI 贡献者未获得对应操作的明确授权时，不暂存、不提交、不推送。提交授权不包含推送或发布 Release；推送授权只覆盖已有提交，不自动吸收未提交改动。

消息结构（以已核实事实替换占位内容，删除不适用项）：

```text
<type>[(scope)][!]: <summary>

<目的、背景和关键取舍>

- <主要能力或行为变化>
- <兼容性、安全边界或迁移影响>

Validation: <实际命令与结果；未验证项及原因>
```

## 版本发布

- commit 正文解释逻辑变更，tag 标识版本，GitHub Release notes 向使用者说明该版本。三者是不同交付物，不能相互替代；只有 tag 不等于已有 GitHub Release。
- 发布前核对 tag、目标提交、包版本和预发布标识。`v1.0.0rc1` 是公开兼容基线，后续公开 MCP tool、CLI 和配置变更须对照该基线评估；候选版本必须标记为预发布。
- 每个新建的公开 GitHub Release 必须有实质说明。首次发布介绍已有能力与边界，后续发布介绍相对上一版本的变化；不能只有版本号、提交标题列表或自动生成的比较链接。
- 提供内容等价的英文和中文发布说明，涵盖：版本定位、主要能力或变化、安装或升级链接、兼容性与迁移要求、已知限制，以及有证据支持的验证情况。明确披露未运行或未通过的检查；本项目没有 GitHub Actions CI，不得声称该 CI 已通过。
- 核对链接，只描述 tag 对应提交已有的内容，不包含未提交或之后提交的变化。说明适用的 Python、zellij 要求和相关 session、Tab、pane 副作用，不作超出文档与验证范围的支持承诺。
- 先准备并审阅说明，再取得明确授权后创建或修改线上 Release。已有 tag 缺少说明时，可在不改动其提交的情况下补充 Release notes，但这不会修复原 commit 正文。改写公开历史、移动已有 tag 或强制推送须另行明确授权，不能作为文档修补的隐含步骤。

## 提交拉取请求

- 修改 MCP 工具、参数或返回结构时同步更新 `SPEC.md`、双语文档、`docs/reference/`、需求覆盖矩阵和测试。
- 修改 zellij 操作契约时同步更新架构、ADR 和真实集成探针。
- 保持 Python 3.7 兼容，不使用仅高版本 Python 支持的语法。
- 不提交凭据、用户 Host 配置、测试缓存、构建产物或开发机绝对路径。
