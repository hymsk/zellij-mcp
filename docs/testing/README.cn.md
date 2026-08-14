# 测试文档

[中文](README.cn.md) | [English](README.md)

- [full-test-plan.cn.md](full-test-plan.cn.md)：direct pane 分层测试计划与质量门禁。
- [requirements-coverage.cn.md](requirements-coverage.cn.md)：根 [SPEC.md](../../SPEC.md) 的 32 项需求覆盖矩阵，含原 24 项 MVP、HTTP/HTTPS 与公开接口要求。
- [test-cases.cn.md](test-cases.cn.md)：11 个 tools 与安全边界用例。

## 验收重点

- `tools/list` 精确返回 11 个 tools。
- 源码和安装后 `tools/list` 均返回完整 annotations 与严格 schema。
- initialize 指引在 360 字符内覆盖用户指定 zellij、持久交互、后台终端任务、已配置远程访问和优先使用 Host 常规执行工具的替代条件。工具描述保留焦点保护、确认完成后的清理及保留例外；创建工具在 420 字符内重复任务选择线索。全部顶层参数有文字说明，boolean 与创建模式默认值与运行时一致；协议 smoke 与质量测试验证这些契约。
- 工具与顶层参数描述合计不超过 5200 字符，不含初始化指导。质量检查同时覆盖输入前检查、新行和按键副作用、完成证据、关闭保护、保留例外和创建重试约束；这是字符预算，不是 token 数。
- `workspace_create` 直接运行 argv command。
- `workspace_list` 与 `tab_list` 返回实时资源和稳定 ID。
- `pane_write_text` 调用 `write-chars`，`pane_send_key` 调用受限 `send-keys`。
- `pane_screen` 支持 viewport、full、ANSI 和 262144 字符上限。
- `pane_close` 与 `tab_close` 要求 `force=true` 并保护特殊目标。
- MCP Host 采用相同 discovery 与 I/O 验收。
- HTTP transport 通过真实 loopback socket 和模拟工具验证握手、11 个 tools、session 隔离、认证、Origin/Host、请求 framing、版本及资源上限；wildcard bind 实测仍只从 loopback 访问，不操作用户 zellij。
- HTTPS 用例在临时目录生成短期自签 certificate/key，验证 TLS 1.2+ 握手与 Bearer 认证，结束后不保留文件。
- 已安装 wheel 的 `source_commit` 与构建 checkout 一致。
- 构建版本读取兼容 Python 3.7 的字符串节点且不执行包初始化；普通 wheel、editable wheel 和预生成元数据均包含完整英文 README 长描述与 Markdown 内容类型。
- 隔离 `ZELLIJ_SOCKET_DIR` 的真实 pane/Tab lifecycle 结束后没有遗留 session。
- Windows/WSL2 按 [Windows 指南](../guides/windows.cn.md#6-验证与排障)分别验证发行版内 doctor、Windows 本机 stdio、NAT 或镜像网络入口及 HTTP/HTTPS 握手；Linux 单元测试通过不代表这些 Windows 场景已验收。

## 执行命令

项目不配置 GitHub Actions CI；根据变更范围在本地执行检查，不能将未执行的检查描述为通过。

```bash
make check
make verify
python3 -m pytest tests/unit/test_http_transport.py -q
make integration-smoke
make integration-installed
make integration-isolated
```

`integration-isolated` 会构建并安装临时 wheel，隔离 `HOME`、`XDG_*`、
`ZELLIJ_CONFIG_DIR` 与 `ZELLIJ_SOCKET_DIR`，创建真实 zellij 资源并清理。

## 文档检查

文档维护至少检查：

- 各语言分区 README 仅索引同语言直属 Markdown 文件。
- 相对链接与标题锚点存在，正文链接保持同一语言。第 3、5 或 7 行的简介导航只允许切换同一页面的语言，不能借此链接另一语言的指南；回归测试覆盖这三种布局。
- 除唯一中文 `SPEC.md` 外，面向人的文档默认使用普通英文 `*.md` 文件，并有对应的 `*.cn.md` 中文翻译；源码树不包含软链接或重复语言别名。回归测试覆盖规范重复版本拒绝、双语引用唯一规范、缺少语言版本、旧别名、跨语言正文链接、过期锚点和软链接元数据拒绝，不创建实际软链接。
- 唯一 `SPEC.md` 与双语需求覆盖矩阵的全部需求 ID 集合一致；原 24 个 MVP ID 保持稳定。
- SPEC 与双语 README、功能及接口参考中的 tool 名称和顺序一致。
- Markdown diff 无空白错误。

```bash
python3 scripts/check_docs.py
python3 -m pytest tests/unit/test_quality_constraints.py -q
git diff --check -- .
```
