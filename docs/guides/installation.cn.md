# 安装与 Host 集成

[中文](installation.cn.md) | [English](installation.md)

Windows 本机运行与对外服务发布见 [Windows/WSL2 指南](windows.cn.md)，包含通过 `wsl.exe` 配置本机 MCP，以及 Windows 端口转发和防火墙步骤。

## 前置条件

`zellij-mcp` 支持 Linux、Python 3.7+ 和 zellij。zellij 需要在 `PATH` 中，并支持以下能力：

- `attach --create-background` 后台创建 session。
- `list-tabs`、`new-tab`、`go-to-tab-by-id`、`rename-tab-by-id` 和 `close-tab-by-id` 稳定 Tab 操作。
- 通过 pane ID 使用 `write-chars`、`send-keys` 和 `dump-screen` 的 direct pane I/O。

这些能力随 zellij 发行版本变化。安装完成后必须以实际环境为准运行 `doctor`，不要仅依赖版本号。

## 安装 zellij

流程顺序为：安装 zellij → 配置 `PATH` → 安装 MCP 运行时包 → 运行 `doctor` → 配置 Host。zellij 安装在 MCP 服务所在的机器上；远程客户端无需安装，除非它也运行本地 MCP 服务。

### 使用官方预编译包

以下 Bash 示例固定使用官方 [v0.45.1 发布版](https://github.com/zellij-org/zellij/releases/tag/v0.45.1)，适用于 `uname -m` 输出为 `x86_64` 或 `aarch64` 的 Linux。需要 `curl`、`tar` 和 GNU coreutils（提供 `sha256sum`、`install`、`cut` 等命令）。用启动 MCP 的同一用户执行，安装到 `~/.local/bin/zellij`，无需 sudo。已有兼容版本时可跳过下载，保留后续版本和能力检查。

```bash
(
  set -eu
  zellij_version=0.45.1
  zellij_target="$(uname -m)-unknown-linux-musl"
  zellij_download_dir=$(mktemp -d)
  trap 'rm -rf "$zellij_download_dir"' EXIT
  cd "$zellij_download_dir"
  zellij_release_url="https://github.com/zellij-org/zellij/releases/download/v$zellij_version"
  curl -fL "$zellij_release_url/zellij-$zellij_target.tar.gz" -o zellij.tar.gz
  curl -fL "$zellij_release_url/zellij-$zellij_target.sha256sum" -o zellij.sha256sum
  tar -xzf zellij.tar.gz zellij
  zellij_sha256=$(cut -d ' ' -f1 zellij.sha256sum)
  printf '%s  zellij\n' "$zellij_sha256" | sha256sum -c -
  install -Dm755 zellij "$HOME/.local/bin/zellij"
)
export PATH="$HOME/.local/bin:$PATH"
command -v zellij
zellij --version
```

发布页的 `.sha256sum` 校验的是解压后的 `zellij`，不是 `.tar.gz`；示例提取摘要并使用本地文件名校验。下载或校验失败时，括号内步骤会停止，不执行安装。临时下载目录自动清理。

`export PATH` 只影响当前 shell。将该行加入用于启动 Host 的 shell 配置，例如 `~/.bashrc`，再打开新终端。若通过桌面程序或服务管理器启动 MCP，也要为该进程配置包含 `~/.local/bin` 的 `PATH`；仅给 MCP 配置绝对 command 路径，不能解决子进程找不到 zellij 的问题。

### 其他安装方式与升级检查

其他架构可参考 [zellij 官方安装文档](https://zellij.dev/documentation/installation.html)。已安装符合 zellij 要求的 Rust 工具链时，也可从源码构建：

```bash
cargo install --locked zellij --version 0.45.1
export PATH="$HOME/.cargo/bin:$PATH"
zellij --version
```

发行版的软件包仓库可能提供较旧版本；通过系统包管理器安装后仍必须运行本项目的 `doctor`。升级时按需修改示例中的版本号，并确认对应发布资产存在。若系统有多个 zellij，先用 `command -v zellij` 确认 MCP 启动环境实际使用的路径；`zellij --version` 成功只证明二进制可运行，不证明所有 MCP 所需能力齐全。

## 安装运行时包

在仓库根目录执行：

```bash
python3 -m pip install .
zellij-mcp version
zellij-mcp doctor --json
```

若 `doctor` 返回非零状态，请先按 `warnings` 和 `fixes` 中的提示安装或升级 zellij，再将 server 配置给 MCP Host。

开发安装包含测试、覆盖率、类型检查、lint 和安全检查工具：

```bash
python3 -m pip install -e ".[dev]"
```

## 配置 MCP Host

任何支持本地 stdio transport 的 MCP Host 都应启动以下命令：

```text
zellij-mcp serve
```

对应的 command 与 args 为：

```json
{
  "command": "zellij-mcp",
  "args": ["serve"]
}
```

将这两个字段放入 Host 指定的 MCP server 配置位置。Host 的配置格式、配置文件位置和重载方式不属于本项目的接口；请查阅所使用 Host 的文档。

若使用虚拟环境，使用该环境中 `zellij-mcp` 的绝对路径，例如：

```json
{
  "command": "/absolute/path/to/.venv/bin/zellij-mcp",
  "args": ["serve"]
}
```

不要以 shell 字符串形式配置 `command`，也不要向 `serve` 的 stdout 写入日志或普通文本。server 的 stdout 是 MCP JSON-RPC 通道。

## Streamable HTTP 连接

默认 `zellij-mcp serve` 仍是 stdio。要以 URL 连接，需单独启动 HTTP 服务：

```bash
# 从安全的配置来源设置 ZELLIJ_MCP_HTTP_TOKEN，不要把真实值写进命令历史或仓库。
zellij-mcp serve --transport streamable-http --host 127.0.0.1 --port 8765
```

环境变量 `ZELLIJ_MCP_HTTP_TOKEN` 是必需的 Bearer token，长度为 32–512 个 ASCII Bearer 字符（字母、数字、`-._~+/` 及可选末尾 `=`）。使用密码管理器生成的高熵随机值；客户端必须发送 `Authorization: Bearer <token>`。token 不是 MCP session ID，也不提供不同客户端之间的资源授权隔离。

客户端选择 **Streamable HTTP**，URL 为 `http://127.0.0.1:8765/mcp`，通过 Host 的安全配置机制提供认证头。HTTP 模式不使用 stdio 的 `command`/`args` 注册结构；服务可以由 A/B/C 中任一受信任节点启动，D 直接连接其 URL，不需要反向代理。具体 URL、headers 和环境变量插值字段取决于 Host，不要直接套用其他 Host 的配置格式。

### HTTP 协议行为

- `POST /mcp` 接收单个 UTF-8 JSON-RPC 对象；请求头需要 `Content-Type: application/json`，以及同时接受 `application/json` 和 `text/event-stream` 的 `Accept`。
- 请求返回 JSON；接受的通知和客户端响应返回 `202` 空体。`GET /mcp` 返回 `405`，不提供 SSE 或旧版 HTTP+SSE 端点。
- 支持协商 `2025-03-26`、`2025-06-18`、`2025-11-25`。初始化后发送 `notifications/initialized`，并在后续请求中携带协商的 `MCP-Protocol-Version` 及初始化响应中的 `MCP-Session-Id`。
- `DELETE /mcp` 结束 MCP session，不关闭它创建的 zellij 资源。MCP session 空闲过期或服务重启后需要重新初始化。
- 最多 64 个 MCP session，空闲 TTL 为 30 分钟；最多 16 个并发连接，请求和响应上限各为 1 MiB，socket 读取超时为 5 秒。每次响应后关闭 HTTP 连接，MCP session 通过请求头延续。
- 每个 MCP session 的工具运行时和创建请求缓存独立；创建去重不跨 session、过期或进程重启。结果不确定时先发现并核实已有资源，不能简单重新初始化并重放创建请求。

### 远程访问与安全边界

`--host` 默认是 `127.0.0.1`，也接受明确的 IPv4/IPv6 literal，例如 `192.0.2.10`、`0.0.0.0`、`::1` 或 `::`；不接受 hostname。`0.0.0.0`/`::` 只控制 socket bind，并不自动接受任意 `Host` 或 `Origin`。HTTP 服务操作的是服务器上启动用户可访问的 zellij，不是客户端的本地终端。

任何非 loopback listener 都必须至少重复提供一次 `--allowed-host`：

- 值可以是 ASCII hostname、IPv4 或方括号 IPv6，并可带端口，例如 `mcp.internal:9443`、`192.0.2.10:8765`、`[2001:db8::10]:8765`。
- 带端口时，请求 `Host` 必须精确命中该端口；不带端口时，匹配 server 的实际 bind port。这个规则允许客户端/隧道使用显式映射端口，同时不会因 wildcard bind 放宽 authority。
- `--allowed-origin` 是可重复的绝对 `http://` 或 `https://` origin；scheme、规范化 host 和有效端口必须精确命中，仅允许空路径或 `/`。不存在 `Origin` 的非浏览器 MCP 客户端不需要配置此项；一旦请求携带 `Origin`，没有白名单匹配就返回 `403`。

推荐直接启用原生 HTTPS，不需要代理：

```bash
zellij-mcp serve --transport streamable-http \
  --host 0.0.0.0 --port 8765 \
  --allowed-host mcp.internal:8765 \
  --tls-cert /secure/config/server-chain.pem \
  --tls-key /secure/config/server-key.pem
```

`--tls-cert` 与 `--tls-key` 必须成对提供，指向 PEM certificate chain 与 private key；server 使用 TLS 1.2 或更高版本。private key 内容不会写入输出，但文件权限和证书签发/轮换由部署者负责。客户端连接 `https://mcp.internal:8765/mcp`，仍必须发送 Bearer token。

如用户明确选择可信内网明文 HTTP，可运行：

```bash
zellij-mcp serve --transport streamable-http \
  --host 0.0.0.0 --port 8765 \
  --allowed-host mcp.internal:8765
```

CLI 会在 stderr 明确警告该 listener 没有 TLS，并推荐 HTTPS；它不会禁止可信私网场景。不要把明文 listener 暴露到公网或不受信网络。

loopback listener 仍可通过安全隧道使用。以下示例在客户端运行，本地映射到 server loopback：

```bash
ssh -N -T -L 127.0.0.1:8765:127.0.0.1:8765 user@server
```

之后客户端仍使用 `http://127.0.0.1:8765/mcp` 和 Bearer token。这里转发的是 **HTTP MCP**，不是把 MCP transport 改成 SSH stdio。若映射后的客户端 `Host` 端口与后端 bind port 不同，在 server 启动参数中显式加入对应的 `--allowed-host host:port`。

默认 loopback 且没有显式 allowlist 时，请求 `Host` 必须是实际 loopback listener 与 bind port；若存在 `Origin`，必须是相同 scheme、host、port。仅配置 `--allowed-origin` 时，Host 仍默认取 listener IP/port；配置 `--allowed-host` 时按该列表判断。显式配置任一 allowlist 后，自动同源 Origin 放行关闭，携带 Origin 的请求必须匹配显式 `--allowed-origin` 列表。不要盲目移除或改写不可信 Origin 来绕过检查；浏览器接入只允许明确列出的 origin。

远程调用应显式指定 `session_name`。HTTP server 的 zellij 上下文来自服务器启动进程，不来自客户端；关闭保护仍会在身份不完整时保守拒绝，不能为了远程使用而禁用保护。

## A/B/C 服务端与 D 客户端示例

以下地址是示例，替换为实际内网 IP。A/B/C 都需要 Linux、Python、兼容的 zellij 和本项目运行时；D 只需支持 Streamable HTTP 的 MCP Host。

| 服务端 | 示例地址 | D 中的连接名称 | D 的 token 环境变量 |
| --- | --- | --- | --- |
| A | `192.168.1.10:8765` | `zellij-a` | `ZELLIJ_A_TOKEN` |
| B | `192.168.1.11:8765` | `zellij-b` | `ZELLIJ_B_TOKEN` |
| C | `192.168.1.12:8765` | `zellij-c` | `ZELLIJ_C_TOKEN` |

### 服务端准备

先在 A/B/C 每台机器按[安装 zellij](#安装-zellij)完成安装，并确保服务进程的 `PATH` 能找到 zellij。然后在各自源码根目录安装到虚拟环境并检查能力：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/zellij-mcp doctor --json
```

为 A/B/C 分别生成并安全保存不同的随机 token，例如使用密码管理器生成 64 位十六进制字符串。服务端环境变量名称统一是 `ZELLIJ_MCP_HTTP_TOKEN`；D 使用表中的三个变量分别保存相应值。不要将真实 token 写入 JSON、源码或 shell 历史。

交互试运行时，可在 Bash 中隐藏输入已有 token：

```bash
read -r -s -p 'MCP token: ' ZELLIJ_MCP_HTTP_TOKEN
export ZELLIJ_MCP_HTTP_TOKEN
```

可信内网 HTTP 下，A 的启动命令如下；B/C 分别替换 `--allowed-host` 中的 IP：

```bash
.venv/bin/zellij-mcp serve --transport streamable-http \
  --host 0.0.0.0 --port 8765 \
  --allowed-host 192.168.1.10:8765
```

`--allowed-host` 指定客户端 URL 中的**服务端地址**，不是 D 的来源 IP。需要允许 IP 和 DNS 名两种访问时重复提供此选项。防火墙来源限制独立配置，建议只允许 D 访问 TCP 8765；不要直接向公网开放明文端口。以上是前台试运行命令，长期运行需要部署者另行配置服务管理与安全凭据注入。

推荐的 HTTPS 只需在上述服务端命令追加成对的 `--tls-cert`、`--tls-key`，并在 D 将 URL 改成 `https://`。证书 SAN 必须匹配 D 使用的域名或 IP，证书链必须被 D 信任；使用私有 CA 时配置客户端信任，不要关闭证书校验。更新证书文件后重启服务以加载新证书。

### D 上配置 OpenCode

将以下 `mcp` 条目合并进 D 的 OpenCode 配置，不要覆盖现有配置。示例使用内网 HTTP；生产使用优先换成已配置证书的 HTTPS 地址：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "zellij-a": {
      "type": "remote",
      "url": "http://192.168.1.10:8765/mcp",
      "oauth": false,
      "headers": { "Authorization": "Bearer {env:ZELLIJ_A_TOKEN}" },
      "enabled": true
    },
    "zellij-b": {
      "type": "remote",
      "url": "http://192.168.1.11:8765/mcp",
      "oauth": false,
      "headers": { "Authorization": "Bearer {env:ZELLIJ_B_TOKEN}" },
      "enabled": true
    },
    "zellij-c": {
      "type": "remote",
      "url": "http://192.168.1.12:8765/mcp",
      "oauth": false,
      "headers": { "Authorization": "Bearer {env:ZELLIJ_C_TOKEN}" },
      "enabled": true
    }
  }
}
```

启动 D 上的 OpenCode 前，确保它继承 `ZELLIJ_A_TOKEN`、`ZELLIJ_B_TOKEN`、`ZELLIJ_C_TOKEN`。本服务使用固定 Bearer token，不提供 OAuth，因此显式设置 `oauth: false`。OpenCode 的 remote 配置格式与环境插值见 [官方 MCP 文档](https://opencode.ai/docs/mcp-servers/)。其他 Host 使用对应的 remote URL 与认证配置。

### 验证与故障定位

1. 在 D 运行 `opencode mcp list` 确认三个连接状态。
2. 分别通过 `zellij-a`、`zellij-b`、`zellij-c` 调用 doctor 与 `workspace_list`，确认返回属于正确机器。
3. 每个服务返回 11 个工具；资源引用必须保留 server 名称以及 `session_name`、`pane_id`/`tab_id`，不能跨服务复用 ID。

| 现象 | 检查项 |
| --- | --- |
| 连接拒绝或超时 | 服务进程、绑定地址、端口、防火墙、D 到服务器的路由 |
| `401` | D 的环境变量是否被 Host 继承、token 是否与对应服务端一致 |
| `403` | URL 的服务端地址/端口是否命中 `--allowed-host`；若带 Origin 是否命中白名单 |
| `400` | 客户端协议版本、session header 或请求格式；优先使用兼容 MCP 客户端 |
| `404` | URL 必须包含 `/mcp`；session 过期时重新初始化 |
| 浏览器 GET 返回 `405` | 正常：此端点使用 POST JSON，不提供浏览器页面或 SSE GET |
| TLS 校验失败 | URL 与证书 SAN、证书有效期、完整证书链及客户端 CA 信任 |
| zellij 操作被拒绝 | 检查服务器用户权限、doctor 能力与当前 pane 保护，不绕过安全检查 |

本配置示例不等价于真实跨机器验收；发布前需在目标网络验证。三个服务的 token 都允许以对应服务端用户身份执行命令，使用受限账户并只向受信任客户端提供。

## 检查连接

Host 连接后调用 `zellij_mcp_doctor`。确认下列能力满足当前工作流：

- `zellij` 可用。
- `zellij_stable_tab_control` 可用。
- `zellij_direct_pane_io` 可用。

调用 `workspace_list` 或 `tab_list` 确认可见资源后，再创建、写入、读取或关闭 pane 与 Tab。完整参数见 [MCP Tools 参考](../reference/mcp-tools.cn.md)。

## 上下文与权限

server 启动时会从同一 Linux 用户的祖先进程中恢复经过白名单校验的 zellij 环境变量，以便识别当前 session 和 pane。即使无法恢复该上下文，server 仍会对资源发现和关闭保护采取保守处理。

server 继承启动它的操作系统用户权限。仅将它配置给受信任的 Host：`workspace_create` 可以执行 argv command，pane 写入 tools 可以向终端程序发送输入。
