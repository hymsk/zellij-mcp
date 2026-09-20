

[中文](README.cn.md) | [English](README.md)
# 手工集成探针

本目录中的 Python 文件是显式运行的手工集成探针，不使用 `test_*.py` 命名，也不会进入默认 pytest 收集。

在仓库根目录完成 `python3 -m pip install -e .` 后，可按需运行：

```bash
make integration-smoke
make integration-installed
make integration-isolated
python3 tests/integration/zellij_create_pane.py
make integration-tab
make integration-pane
make integration-safety
# 或验证已安装的 CLI：
python3 tests/integration/zellij_tab_lifecycle.py zellij-mcp serve
python3 tests/integration/zellij_pane_lifecycle.py zellij-mcp serve
python3 tests/integration/zellij_pane_safety.py
```

`integration-installed` 构建 wheel 并校验英文 README 长描述，安装后从仓库外执行严格 `tools/list` smoke 与
provenance 检查，不创建 zellij 资源。`integration-isolated` 使用独立 HOME、XDG 目录和
`ZELLIJ_SOCKET_DIR`，通过已安装 wheel 执行真实 pane/Tab lifecycle，并断言没有遗留 session。

除 smoke 外的其他探针会操作真实 zellij pane/Tab，仅支持 zellij；执行前确认当前 session，执行后复查 `workspace_list` 和 `tab_list`。
`zellij_pane_lifecycle.py` 只通过 MCP stdio 创建唯一 session，并按 `(session_name, pane_id)` 执行 create/list/write-text/send-key/screen/close；失败清理也通过新的 MCP 进程完成，不调用 zellij shell。
`zellij_tab_lifecycle.py` 只通过 MCP stdio 创建唯一 session，验证稳定 Tab ID、detached focus 三态、`new-pane --tab-id` 路由、Tab 关闭和最终 pane 资源归零。
`zellij_pane_safety.py` 只通过 MCP stdio 验证当前 MCP pane、plugin pane 和未知 pane 均拒绝关闭，并确认失败操作不改变 pane 基线；任何工具错误都会返回非零退出码。
`zellij_create_pane.py` 默认自动清理，只有显式传入 `--keep` 才保留新 pane。
