
# Zellij MCP Repository Rules

本文件适用于本仓库根目录及其子目录。

## 项目边界

- 当前复用器只支持 zellij，不实现或降级到 tmux/screen。
- Python 代码尽可能兼容 Python 3.7，禁止使用仅高版本 Python 支持的类型注解语法。
- MCP 是 zellij 操作的正式接口；外部 skill 或 shell zellij 只能用于明确的独立排障，不得静默替代 MCP。

## 文档维护

- 根 `SPEC.md` 是唯一规范，仅维护中文，统一管理需求、公开行为与验收标准，不另建翻译或别名。行为变更先更新 SPEC，再同步实现和验证，不把未实现方案写成当前能力。
- 除 `SPEC.md` 外，面向人的 Markdown 文档以无语言后缀的 `*.md` 保存英文正文，以 `*.cn.md` 保存对应中文翻译，包括 README、贡献、安全、指南、参考、架构、ADR 与测试说明。本文件属于 AI 规则，保持中文即可。
- 仓库文件不使用软链接。`README.md`、各目录索引等均为普通英文文件，`SPEC.md` 为普通中文文件；不保留 `*.en.md`、`README.zh-cn.md` 等重复别名。包元数据直接引用 `README.md`。
- 中文正文只链接中文版本，英文正文只链接英文版本；唯一规范 `SPEC.md` 可由两种语言共同引用。仅简介内的语言切换行链接同页的另一语言版本；普通页面放在第 3 行，仅含一句话定位的首页放在第 5 行，另有介绍段落时放在第 7 行，可追加同语言导航。各语言目录页只索引同语言文档。链接包含锚点时须同步使用目标语言的标题锚点。
- `docs/` 保存详细指南、接口参考、架构、ADR 和测试证据；需求页面只索引 SPEC，不另立需求基线。
- 架构变化同步更新 `docs/architecture/` 和对应 ADR。
- 人机交互边界变化同步更新 `docs/design/human-ai-handoff.md` 与 `docs/design/human-ai-handoff.cn.md`。
- MCP tool、返回结构或能力边界变化同步更新 `SPEC.md`、`docs/reference/` 和双语 README。
- 测试场景、验证结果或运行命令变化同步更新 `docs/testing/`。
- 当前文档只描述已实现且可验证的行为；过程记录和内部验收材料不进入本仓库。

## 验证要求

- Python 修改至少运行 `python3 -m compileall -q zellij_mcp tests scripts`。
- 行为修改运行 `python3 -m pytest tests -q`。
- 文档修改运行 `python3 scripts/check_docs.py`、`python3 -m pytest tests/unit/test_quality_constraints.py -q` 和 `git diff --check -- .`，确保唯一中文 SPEC、其余文档双语配对、同语言链接、标题锚点及无软链接，并验证 SPEC 与双语覆盖矩阵的需求 ID、双语 README/参考文档的 tool 集合一致。
- 本项目不配置 GitHub Actions CI，仍须执行与变更相关的本地检查；不能将未运行的检查描述为通过。

## 公开兼容基线

- `v1.0.0rc1` 是当前公开兼容基线；从该 tag 开始维护公开 MCP tool、CLI 和配置行为的向后兼容。
- 独立源码仓库之外的旧目录布局、CodeAgent adapter 和 Host 注册器不属于本仓库兼容范围。
- 不在源码、文档、测试和构建产物中记录个人邮箱、个人服务地址、凭据或开发机绝对路径。
