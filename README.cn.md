# zellij-mcp

> Zellij-MCP 让 AI 通过 MCP 管理本机或远程服务器上的 zellij 会话、标签页和终端窗格，运行命令、查看输出并与终端程序交互。

[中文](README.cn.md) | [English](README.md) · [文档](docs/README.cn.md) · [规范](SPEC.md) · [安全政策](SECURITY.cn.md) · [贡献指南](CONTRIBUTING.cn.md)

## 使用场景

- **持续交互**：让 AI 在同一个 GDB、Python REPL 或数据库命令行会话中反复操作，保留上下文。甚至可以让其操作另一个 Harness，做 Runtime / 插件 等真实运行测试。
- **远程后台任务**：在独立窗格中运行构建、测试或服务，让 AI 按需查看进度、日志并继续操作。
- **敏感信息输入**：让 AI 创建专用 Tab，运行不回显输入的程序，由你在终端输入密钥或 token；程序接收后，AI 可继续驱动它使用这些凭据完成认证、配置等操作，无需将凭据粘贴到对话中。

Zellij-MCP 不会自动监控任务或脱敏；隐藏输入由窗格内的程序实现，不是专用的凭据捕获接口。不回显不等于对 AI 保密：若程序将凭据输出并被 AI 读取，凭据仍会进入模型上下文。

## 安装与连接

按终端所在的位置，选择**本地使用**或**远程使用**。MCP Host 指使用这些工具的 AI 客户端，例如 OpenCode。

每个场景开头都提供了可直接发给 AI 的配置指令，将方括号内容替换为实际信息即可；不要在提示词中填写真实 token 或其他凭据。

| 方式 | 适用场景 | 需要准备 |
| --- | --- | --- |
| [本地使用](#本地使用) | 让 AI 操作当前机器的终端 | 本机安装 zellij 和 Zellij-MCP，由 Host 通过 stdio 启动 |
| [远程使用](#远程使用) | 让 AI 操作远程机器的终端 | 在目标机器部署服务端，再由 Host 通过 URL 和 token 连接；已有服务时只需配置客户端 |

### 本地使用

**一句话让 AI 配置：**

```text
请克隆 https://github.com/hymsk/zellij-mcp.git（已有源码则复用，保留本地改动），按照 README.cn.md「本地使用」及 docs/guides/installation.cn.md，在我的 [操作系统] 上安装 zellij 和 Zellij-MCP，为 [MCP Host 名称] 配置本地 stdio 连接并验证可用性，不启用网络监听，保留其他配置，缺少信息先问我。
```

环境要求：Linux、支持 pip 和 venv 的 Python 3.7+、Git，以及可从 `PATH` 找到的 zellij。Windows 请在 [WSL2](docs/guides/windows.cn.md) 内运行服务，不支持原生 Windows。

先[安装 zellij](docs/guides/installation.cn.md#安装-zellij)，再将 Zellij-MCP 安装到虚拟环境：

```bash
git clone https://github.com/hymsk/zellij-mcp.git
cd zellij-mcp
python3 -m venv --copies .venv
. .venv/bin/activate
python3 -m pip install .
zellij-mcp doctor --json
```

`doctor` 检查 zellij 的实际能力，而不只检查版本号。连接前，先按 `warnings` 和 `fixes` 处理问题。运行 `zellij-mcp version --json` 可确认安装产物来源。

然后在 Host 中注册本地 stdio 服务。需要启动的命令及参数为：

```json
{
  "command": "/absolute/path/to/zellij-mcp/.venv/bin/zellij-mcp",
  "args": ["serve"]
}
```

将示例路径替换为实际安装路径。这是启动字段示意，不是适用于所有 Host 的完整配置；字段格式、配置位置和重载方式以所用 Host 为准。确保 Host 启动的服务进程能从 `PATH` 找到 zellij。

本地 stdio 由 Host 启动，不监听网络端口，也不需要 HTTP token。无需另起 HTTP 服务，`serve` 的 stdout 专用于 MCP JSON-RPC。

### 远程使用

远程使用分为服务端部署和客户端连接两部分：服务端运行在需要被操作的机器上，客户端通过 Streamable HTTP/HTTPS 调用它。若已有可用服务，可直接跳到[连接服务端](#连接服务端)，客户端无需安装 zellij 或 Zellij-MCP。

#### 部署服务端

**一句话让 AI 部署：**

```text
请在 [目标服务器与操作系统] 上克隆 https://github.com/hymsk/zellij-mcp.git（已有源码则复用，保留本地改动），按照 README.cn.md「部署服务端」及 docs/guides/installation.cn.md 安装并部署 Zellij-MCP，使用最小权限账户、Bearer token 和 HTTPS 或安全隧道，在确认监听地址与访问范围后配置服务并验证可用性，凭据通过安全方式注入且不回显，保留无关配置，缺少信息先问我。
```

在**需要被操作的机器上**，先按[本地使用](#本地使用)中的安装步骤完成 zellij、Zellij-MCP 安装和 `doctor` 检查，不必配置本地 Host。随后独立启动 Streamable HTTP/HTTPS 服务。

**先配置 token。** HTTP 模式必须设置服务端环境变量 `ZELLIJ_MCP_HTTP_TOKEN`；即使只监听本机地址，也不能省略认证。使用密码管理器生成并保存高熵随机值，例如 64 位十六进制字符串。合法 token 为 32–512 个 ASCII Bearer 字符，具体格式见[认证说明](docs/guides/installation.cn.md#streamable-http-连接)。

交互试运行时，可在 Bash 中隐藏输入已有 token，避免将真实值写入命令历史：

```bash
read -r -s -p 'MCP token: ' ZELLIJ_MCP_HTTP_TOKEN
printf '\n'
export ZELLIJ_MCP_HTTP_TOKEN
```

**远程直连优先使用 HTTPS。** 准备好客户端信任的证书和私钥，在已激活的安装环境中启动：

```bash
zellij-mcp serve --transport streamable-http \
  --host 0.0.0.0 --port 8765 \
  --allowed-host mcp.example.com:8765 \
  --tls-cert /secure/config/server-chain.pem \
  --tls-key /secure/config/server-key.pem
```

将 `mcp.example.com` 和证书路径替换为实际值。客户端连接 `https://mcp.example.com:8765/mcp`；域名需指向服务端，证书需覆盖该域名，证书链需被客户端信任。使用私有 CA 时配置客户端信任，不要关闭证书校验。

部署前务必确认：

- **token 代表终端操作权限。** 获准客户端可以执行命令、读取终端内容和发送输入，权限等同于启动服务的操作系统用户；这不是沙箱，也不提供多租户隔离。建议使用专用、最小权限账户，不要以 root 启动。
- **限制网络入口。** `0.0.0.0` 监听所有 IPv4 网卡，可改为所需的具体 IP。防火墙应只允许受信任客户端访问端口；不要将明文 HTTP 暴露到公网或不受信网络。
- **Host 白名单不是客户端 IP 白名单。** `--allowed-host` 填客户端 URL 中的服务端域名与端口。若客户端发送 `Origin`，还需通过 `--allowed-origin` 明确允许该来源，不要绕过校验。
- **保护凭据。** 不要把真实 token 放进 README、JSON 配置、URL、命令行参数或日志。每个服务使用独立 token，通过安全渠道交给客户端；泄露后更换 token、重启服务并更新客户端配置。

没有 HTTPS 证书时，可只监听 `127.0.0.1`，通过 [SSH 安全隧道](docs/guides/installation.cn.md#远程访问与安全边界)连接，仍然需要 Bearer token。上述命令是前台试运行；长期运行请另行配置服务管理、凭据注入和证书维护。

#### 连接服务端

**一句话让 AI 连接：**

```text
请阅读 https://github.com/hymsk/zellij-mcp 的 README.cn.md「连接服务端」及 docs/guides/installation.cn.md，为我的 [MCP Host 名称] 配置指向 [服务 URL] 的 Streamable HTTP 连接，通过安全方式注入服务端提供的 Bearer token，保留 TLS 校验和现有其他配置，并验证连接及目标机器身份；无需克隆仓库或在客户端安装 zellij、Zellij-MCP，也不要修改远程服务，缺少信息先问我。
```

如果服务已由你或管理员部署好，客户端只需支持 **Streamable HTTP** 的 MCP Host，无需安装 Python、zellij 或 Zellij-MCP。向服务端管理员取得：

- 服务 URL，例如 `https://mcp.example.com:8765/mcp`，注意保留 `/mcp` 路径。
- 对应的 Bearer token，通过安全渠道获取并保存。
- 如使用私有 CA，取得证书信任配置，而不是关闭 TLS 校验。

以 OpenCode 为例，将以下条目合并到现有配置，不要覆盖其他配置：

```json
{
  "mcp": {
    "zellij-remote": {
      "type": "remote",
      "url": "https://mcp.example.com:8765/mcp",
      "oauth": false,
      "headers": {
        "Authorization": "Bearer {env:ZELLIJ_REMOTE_TOKEN}"
      },
      "enabled": true
    }
  }
}
```

替换 URL，并在启动 OpenCode 前通过安全方式设置 `ZELLIJ_REMOTE_TOKEN`，使 OpenCode 进程继承它。**该值必须与服务端的 `ZELLIJ_MCP_HTTP_TOKEN` 一致**；变量名可以不同，不要在客户端重新生成另一个 token。本服务使用 Bearer token，不提供 OAuth，因此设置 `oauth: false`。

其他 Host 使用各自的远程 MCP 配置格式，选择 Streamable HTTP 并提供 `Authorization: Bearer <token>`；不要使用本地 stdio 的 `command`/`args` 配置，也不要选择旧版 HTTP+SSE。

连接后先调用 `zellij_mcp_doctor` 和 `workspace_list`，确认发现的是目标服务器的资源。连接多个服务时分别命名并使用各自的 token，资源 ID 不能跨服务复用。多机器配置及 `401`、`403`、TLS 等排障见[远程连接指南](docs/guides/installation.cn.md#abc-服务端与-d-客户端示例)。

## 卸载

**一句话让 AI 卸载：** 按实际情况填写卸载范围。

```text
请按 https://github.com/hymsk/zellij-mcp 的 README.cn.md「卸载」步骤，为我移除 [目标机器 / MCP Host] 上的 [本地安装 / 服务端 / 仅远程连接]，先确认安装与配置位置，仅清理选定范围并验证结果，保留其他配置、zellij 及运行中的任务，删除源码或凭据前先问我。
```

根据安装方式处理：

| 卸载范围 | 操作 |
| --- | --- |
| 本地安装 | 从 Host 移除对应 MCP 配置并重载，确认本地 MCP 进程已停止，再卸载包 |
| 服务端 | 停止对应 HTTP/HTTPS 服务；若配置了服务管理器，同时禁用该服务的自动启动，再在服务器上卸载包 |
| 仅远程连接 | 从 Host 移除对应连接并重载即可，不停止或卸载远程服务 |

需要卸载包时，在**原安装环境**中执行：

```bash
python3 -m pip uninstall zellij-mcp
```

卸载包不会关闭 zellij 会话或停止窗格内的命令。源码、虚拟环境、凭据、证书，以及为该服务配置的防火墙规则或隧道不会随包自动清理；确认不再使用后再单独处理，避免影响共享资源。

## 工具一览

| 工具 | 作用 |
| --- | --- |
| `zellij_mcp_doctor` | 检查运行环境、zellij 能力和服务端上下文 |
| `workspace_create` | 创建会话、标签页或窗格，并运行指定命令 |
| `workspace_list` | 发现现有会话与窗格，区分终端和插件窗格 |
| `tab_list` | 列出标签页 ID、活动状态及所含窗格 |
| `tab_focus` | 切换到指定标签页 |
| `tab_rename` | 重命名标签页 |
| `tab_close` | 关闭标签页，需显式设置 `force=true` |
| `pane_write_text` | 向终端窗格发送文本 |
| `pane_send_key` | 向终端窗格发送一个支持的按键 |
| `pane_screen` | 读取当前屏幕或可用滚动历史，可保留 ANSI 转义序列 |
| `pane_close` | 关闭终端窗格，需显式设置 `force=true` |

stdio 和 HTTP/HTTPS 提供相同的 11 个工具。资源 ID 来自发现结果，并与所属服务、会话一起使用；参数、返回值和限制见[工具参考](docs/reference/mcp-tools.cn.md)。

## 开发与贡献

在源码目录中激活开发用虚拟环境，然后执行：

```bash
python3 -m pip install -e ".[dev]"
make verify
```

`make verify` 运行静态检查、编译、单元测试及文档检查。真实 zellij 集成测试需单独运行，会创建和关闭终端资源，详见[测试文档](docs/testing/README.cn.md)。

提交改动前请阅读[贡献指南](CONTRIBUTING.cn.md)；公开行为以[规范](SPEC.md)为准。

## 许可证

[AGPL-3.0-or-later](LICENSE)。
