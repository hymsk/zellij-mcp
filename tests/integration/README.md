# Manual Integration Probes

[中文](README.cn.md) | [English](README.md)

Python files in this directory are explicitly run manual integration probes. They do not use `test_*.py` names and are not collected by default pytest runs.

After `python3 -m pip install -e .` from the repository root, run as needed:

```bash
make integration-smoke
make integration-installed
make integration-isolated
python3 tests/integration/zellij_create_pane.py
make integration-tab
make integration-pane
make integration-safety
# Or verify the installed CLI:
python3 tests/integration/zellij_tab_lifecycle.py zellij-mcp serve
python3 tests/integration/zellij_pane_lifecycle.py zellij-mcp serve
python3 tests/integration/zellij_pane_safety.py
```

`integration-installed` builds a wheel, verifies its English README long description, and installs it, then runs strict `tools/list` smoke and provenance checks from outside the repository without creating zellij resources. `integration-isolated` uses independent HOME, XDG directories, and `ZELLIJ_SOCKET_DIR`, runs real pane/Tab lifecycle checks through the installed wheel, and asserts no leftover sessions.

Probes other than smoke operate real zellij panes/Tabs and support only zellij. Confirm the current session before execution and recheck `workspace_list` and `tab_list` afterward.

`zellij_pane_lifecycle.py` creates a unique session only through MCP stdio and performs create/list/write-text/send-key/screen/close using `(session_name, pane_id)`. Failure cleanup also uses a new MCP process, without shell zellij calls.

`zellij_tab_lifecycle.py` creates a unique session only through MCP stdio and verifies stable Tab IDs, three-state detached focus, `new-pane --tab-id` routing, Tab closing, and zero remaining pane resources.

`zellij_pane_safety.py` uses only MCP stdio to verify refusal to close the current MCP pane, plugin panes, and unknown panes, and confirms failed operations leave the pane baseline unchanged. Any tool error produces a nonzero exit code.

`zellij_create_pane.py` cleans up automatically by default; only explicit `--keep` retains the new pane.
