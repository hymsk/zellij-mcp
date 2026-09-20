# Windows 本机 MCP 配置与服务发布

[中文](windows.cn.md) | [English](windows.md)

本文说明 Windows 特有的部署步骤：在 WSL2 中运行 zellij 和 MCP，由 Windows 上的 Host 通过 `wsl.exe` 启动本机 stdio 服务，或将 WSL2 内的 HTTP/HTTPS 服务开放给其他机器。远程客户端的配置复用[安装指南](installation.cn.md#streamable-http-连接)。

本项目的运行时基线是 Linux。Windows 上按 WSL2 的 Linux 环境部署，不将原生 Windows Python 与 `zellij.exe` 组合视为已支持的运行方式。下文使用发行版名称 `Ubuntu`；使用其他名称时，替换所有命令中的发行版名称。

| 使用方式 | 服务进程 | Windows 需要配置什么 |
| --- | --- | --- |
| Windows Host 使用本机 zellij | Host 通过 `wsl.exe` 启动 WSL2 中的 stdio MCP | 本机 MCP 启动命令；无需监听端口 |
| 其他机器访问 Windows 提供的服务 | WSL2 中独立运行 HTTP/HTTPS MCP | WSL 监听、Windows 网络入口和防火墙 |

## 1. 准备 WSL2 环境

适用于 Windows 11，或支持 `wsl --install` 的 Windows 10 2004 / Build 19041 及以上版本。在**管理员 PowerShell**中安装；已经安装 WSL2 和目标发行版时跳过安装命令：

```powershell
wsl.exe --install -d Ubuntu
```

按安装提示重启 Windows，首次打开 Ubuntu 后完成 Linux 用户初始化。随后在 PowerShell 中检查：

```powershell
wsl.exe --update
wsl.exe --list --verbose
```

确认 Ubuntu 的 `VERSION` 为 `2`；如果仍为 `1`，先保存发行版中的工作，再执行 `wsl.exe --set-version Ubuntu 2`。进入 Ubuntu：

```powershell
wsl.exe --distribution Ubuntu
```

后续标为 Bash 的命令都在 Ubuntu 内执行，标为 PowerShell 的命令在 Windows 执行。

### 安装 zellij 和 MCP

在 Ubuntu 中准备依赖：

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip curl ca-certificates tar coreutils git
```

先按[安装 zellij](installation.cn.md#安装-zellij)安装 Linux 版 zellij，并配置 `PATH`。然后安装 MCP 到该 Linux 用户的虚拟环境；已有源码时使用现有检出目录，跳过 clone：

```bash
mkdir -p "$HOME/src"
git clone https://github.com/hymsk/zellij-mcp.git "$HOME/src/zellij-mcp"
python3 -m venv "$HOME/.local/share/zellij-mcp/venv"
"$HOME/.local/share/zellij-mcp/venv/bin/python" -m pip install "$HOME/src/zellij-mcp"
"$HOME/.local/share/zellij-mcp/venv/bin/zellij-mcp" doctor --json
```

`doctor` 返回非零状态时，先解决 zellij 路径或能力问题，再配置 Host。Windows 本机 Host 和对外服务应使用同一发行版、同一 Linux 用户，才能操作同一组 zellij 资源。

### 创建不依赖交互 shell 的启动入口

Windows Host 启动 `wsl.exe` 时不应依赖 `.bashrc` 激活虚拟环境。以下入口显式设置 zellij 的查找路径，并直接启动虚拟环境中的 MCP；脚本不向 stdout 输出额外文字。

在 Ubuntu 中执行：

```bash
(
  set -eu
  zellij_launcher=$(mktemp)
  trap 'rm -f "$zellij_launcher"' EXIT
  cat > "$zellij_launcher" <<'SH'
#!/bin/sh
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
exec "$HOME/.local/share/zellij-mcp/venv/bin/zellij-mcp" "$@"
SH
  sudo install -m 0755 "$zellij_launcher" /usr/local/bin/zellij-mcp-wsl
)
```

回到 Windows PowerShell，通过将来 Host 使用的入口检查：

```powershell
wsl.exe --distribution Ubuntu --exec /usr/local/bin/zellij-mcp-wsl doctor --json
```

这一步成功后，再配置 stdio。不要手动运行 `serve` 来判断是否“卡住”：它会等待 Host 从 stdin 发送 MCP 请求。

## 2. 配置 Windows 本机 MCP

本节适用于 Host 进程运行在 Windows、服务进程运行在 WSL2 的情况。如果 Host 本身就在 WSL2 中运行，直接使用[Linux stdio 配置](installation.cn.md#配置-mcp-host)。

### OpenCode

编辑 Windows 用户的 `%USERPROFILE%\.config\opencode\opencode.json`；若已设置 `OPENCODE_CONFIG`，使用它指定的配置文件。将以下条目合并到现有 `mcp` 对象，不覆盖其他配置：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "zellij-wsl": {
      "type": "local",
      "command": [
        "wsl.exe",
        "--distribution", "Ubuntu",
        "--exec", "/usr/local/bin/zellij-mcp-wsl",
        "serve"
      ],
      "enabled": true
    }
  }
}
```

重新启动 OpenCode，在 PowerShell 中运行 `opencode mcp list` 检查连接。需要固定 Linux 用户时，在 `--exec` 前加入 `--user` 和实际用户名；不要让 Host 以 root 用户意外启动另一组 zellij 资源。

### Codex CLI

在 Windows PowerShell 中注册同一个 stdio 入口：

```powershell
codex mcp add zellij-wsl -- wsl.exe --distribution Ubuntu --exec /usr/local/bin/zellij-mcp-wsl serve
codex mcp list
```

先确认当前版本的 `codex mcp add --help` 支持上述 `-- <COMMAND>...` 形式。CLI 使用其当前用户配置；Windows 与 WSL 内各自运行的 Codex 是不同进程环境，不能把在 WSL 内注册的配置当成 Windows 配置已完成。已有同名条目时先检查并修改该条目。

重启 Host 后调用 `zellij_mcp_doctor` 和 `workspace_list`，确认发现 11 个工具，资源属于预期的 WSL 发行版及 Linux 用户。配置条目存在不等于 MCP 握手或资源操作已经通过。

## 3. 在 WSL2 内启动对外服务

对外服务需要独立启动 HTTP/HTTPS 进程，不能把本机 stdio 的 stdin/stdout 直接映射成 TCP 端口。客户端的 URL、Bearer 认证及 MCP 协议要求统一见[安装指南](installation.cn.md#streamable-http-连接)。

以下使用 Windows 局域网地址 `192.168.1.20`、端口 `8765`，允许访问的客户端地址为 `192.168.1.50`。这些均为示例，请替换为实际地址。

在 Ubuntu 中通过隐藏输入设置已有的高熵 token，再启动服务：

```bash
read -r -s -p 'MCP token: ' ZELLIJ_MCP_HTTP_TOKEN
export ZELLIJ_MCP_HTTP_TOKEN
/usr/local/bin/zellij-mcp-wsl serve --transport streamable-http \
  --host 0.0.0.0 --port 8765 \
  --allowed-host 192.168.1.20:8765
```

token 使用[安装指南](installation.cn.md#streamable-http-连接)规定的 32–512 个 ASCII Bearer 字符。上述 HTTP 示例适用于可信私网；保持这个终端和 WSL 实例运行，直到完成连通性验证。

- `--host 0.0.0.0` 允许来自 Windows 转发入口的连接；只监听 WSL 的 `127.0.0.1` 不能通过 NAT 转发访问。
- `--allowed-host` 填客户端 URL 中的 Windows IP 或 DNS 名及端口，不填客户端 IP，也不机械填写 WSL 内部地址。端口转发保留 HTTP Host 头。
- 如果还要从 Windows 本机以 `127.0.0.1` 测试，可额外加入 `--allowed-host 127.0.0.1:8765`。
- `workspace_create` 执行的是 WSL 中的 Linux 命令；`cwd` 也使用 Linux 路径。需要访问 Windows 文件时使用对应的 `/mnt/c/...` 路径。

### 启用 HTTPS

需要跨不受信任网络访问时，为客户端使用的 DNS 名准备受信任的证书，将证书链和私钥保存在 WSL 中。以下示例假定客户端使用 `mcp.example.com`，Windows 和 WSL 两侧均使用端口 `8765`：

```bash
/usr/local/bin/zellij-mcp-wsl serve --transport streamable-http \
  --host 0.0.0.0 --port 8765 \
  --allowed-host mcp.example.com:8765 \
  --tls-cert "$HOME/.config/zellij-mcp/server-chain.pem" \
  --tls-key "$HOME/.config/zellij-mcp/server-key.pem"
```

仍须先设置 `ZELLIJ_MCP_HTTP_TOKEN`。证书 SAN 必须包含实际 DNS 名，客户端必须信任证书链；`mcp.example.com` 仅为示例。Windows 端口转发透传 TLS，不需要在 Windows 端终止 HTTPS。

## 4. 通过 Windows 开放网络入口

### WSL2 默认 NAT 模式

先让第 3 节的服务保持运行。在**管理员 PowerShell**中设置实际地址并获取 WSL IPv4：

```powershell
$ZellijWindowsIp = "192.168.1.20"
$ZellijClientIp = "192.168.1.50"
$ZellijWslAddresses = wsl.exe --distribution Ubuntu --exec hostname -I
if ($LASTEXITCODE -ne 0) { throw "无法查询 WSL 地址" }
$ZellijWslIp = ($ZellijWslAddresses -split '\s+' |
  Where-Object { $_ -match '^\d{1,3}(\.\d{1,3}){3}$' } |
  Select-Object -First 1)
if (-not $ZellijWslIp) { throw "未找到 WSL IPv4 地址" }
$ZellijWslIp
```

确认选中的是 Ubuntu 的 WSL 网络地址；存在 Docker 等多个网络接口时，结合 Ubuntu 内的 `ip -4 addr show eth0` 核实，必要时手动设置 `$ZellijWslIp`。`hostname -I` 使用大写 `I`。

创建 TCP 转发，并为该客户端添加入站规则：

```powershell
netsh interface portproxy add v4tov4 listenaddress=$ZellijWindowsIp listenport=8765 connectaddress=$ZellijWslIp connectport=8765
New-NetFirewallRule -Name "ZellijMCP-8765" -DisplayName "Zellij MCP 8765" -Direction Inbound -Action Allow -Protocol TCP -LocalAddress $ZellijWindowsIp -LocalPort 8765 -RemoteAddress $ZellijClientIp -Profile Private
netsh interface portproxy show v4tov4
```

示例适用于可信的 `Private` 网络配置文件；用 `Get-NetConnectionProfile` 确认实际类型，域网络按组织策略调整。不要为解决连通性问题关闭整个防火墙。`--allowed-host` 负责 HTTP 访问地址校验，`-RemoteAddress` 才是这里的客户端来源限制。

WSL 重启后内部 IP 可能改变。重新查询地址，并仅更新本服务的转发项：

```powershell
netsh interface portproxy set v4tov4 listenaddress=$ZellijWindowsIp listenport=8765 connectaddress=$ZellijWslIp connectport=8765
```

该命令使用重新查询后的变量；防火墙规则已存在时无需重复创建。Windows 局域网地址变化时，还需更新监听地址、规则及服务端 `--allowed-host`。

### 已使用镜像网络的 Windows 11

Windows 11 22H2 及以上版本可配置 WSL 的 `networkingMode=mirrored`。如果当前已经使用该模式，直接访问镜像网络中的服务，跳过 NAT 的 `portproxy` 步骤；无需为了本项目修改全局 WSL 网络模式。

按实际策略放行 Windows/Hyper-V 防火墙的 TCP 8765。微软文档提供的端口级 Hyper-V 规则形式如下，在管理员 PowerShell 中执行，不全局放开 WSL 入站：

```powershell
New-NetFirewallHyperVRule -Name "ZellijMCP-8765" -DisplayName "Zellij MCP 8765" -Direction Inbound -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -Protocol TCP -LocalPorts 8765
```

客户端来源范围仍应由实际 Windows/Hyper-V 网络策略限制。镜像网络的系统版本、配置及防火墙要求见[微软 WSL 网络文档](https://learn.microsoft.com/en-us/windows/wsl/networking#mirrored-mode-networking)。

### 公网或跨网段入口

仅配置 Windows 转发并不会自动配置路由器、云安全组或 DNS。需要直连时，另外建立到 Windows 实际监听地址和端口的路由/转发，并使用 HTTPS；也可复用[安全隧道方案](installation.cn.md#远程访问与安全边界)。外部 URL 的 DNS 名和端口必须命中 `--allowed-host`，证书覆盖该 DNS 名。公网映射为不同端口时，白名单也要使用外部端口。

## 5. 长期运行与停止

前台运行时退出服务进程会停止 MCP；关闭 WSL、Windows 关机或睡眠也会影响可用性。需要进程管理时，可在已启用 systemd 的 WSL 发行版中配置用户服务。

先用 `systemctl --user status` 确认用户服务管理器可用；尚未启用时，按[微软 systemd 指南](https://learn.microsoft.com/en-us/windows/wsl/systemd)配置，重启 WSL 前保存现有工作。以下仍以可信私网 HTTP 为例。

在 Ubuntu 中创建私有配置目录，隐藏输入 token 并写入环境文件：

```bash
(
  set -eu
  umask 077
  mkdir -p "$HOME/.config/zellij-mcp"
  read -r -s -p 'MCP token: ' ZELLIJ_MCP_HTTP_TOKEN
  printf 'ZELLIJ_MCP_HTTP_TOKEN=%s\n' "$ZELLIJ_MCP_HTTP_TOKEN" > "$HOME/.config/zellij-mcp/http.env"
  chmod 600 "$HOME/.config/zellij-mcp/http.env"
)
mkdir -p "$HOME/.config/systemd/user"
```

将以下内容保存为 `~/.config/systemd/user/zellij-mcp.service`，按实际地址修改启动参数；HTTPS 部署使用第 3 节的 DNS 白名单和证书参数：

```ini
[Unit]
Description=Zellij MCP

[Service]
Type=simple
EnvironmentFile=%h/.config/zellij-mcp/http.env
ExecStart=/usr/local/bin/zellij-mcp-wsl serve --transport streamable-http --host 0.0.0.0 --port 8765 --allowed-host 192.168.1.20:8765
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

先停止占用同一端口的前台实例，再启动用户服务：

```bash
systemctl --user daemon-reload
systemctl --user enable --now zellij-mcp.service
systemctl --user status zellij-mcp.service
journalctl --user -u zellij-mcp.service -n 50 --no-pager
```

`enable` 作用于 WSL 内的用户服务管理器，不等于注册了 Windows 开机服务。微软明确说明 systemd 服务本身不会保持 WSL 实例存活；Windows 重启后需重新启动发行版和用户服务，并检查 NAT 地址。持续运行还需要 Windows 的启动及电源策略配合。

停止并取消用户服务启动：

```bash
systemctl --user disable --now zellij-mcp.service
```

取消对外入口时，在管理员 PowerShell 中仅删除本指南创建的规则，地址使用当时的实际监听地址：

```powershell
netsh interface portproxy delete v4tov4 listenaddress=192.168.1.20 listenport=8765
Remove-NetFirewallRule -Name "ZellijMCP-8765"
```

如果配置过镜像网络的 Hyper-V 规则，单独执行 `Remove-NetFirewallHyperVRule -Name "ZellijMCP-8765"`。没有创建的规则无需删除，不使用 `portproxy reset` 清除其他服务的转发。停止 MCP 不会自动关闭已经创建的 zellij 资源。

## 6. 验证与排障

1. Ubuntu 内执行 `/usr/local/bin/zellij-mcp-wsl doctor --json`，确认运行环境可用。
2. Windows 通过同一 `wsl.exe` 命令执行 doctor，确认发行版、用户、路径一致；本机 stdio 随后由 Host 发现工具。
3. 发布服务后，在目标客户端运行 `Test-NetConnection 192.168.1.20 -Port 8765`，先确认 TCP 可达。该检查不验证 Bearer、TLS 或 MCP 握手。
4. 按[通用连接流程](installation.cn.md#检查连接)验证 MCP 初始化、11 个工具和目标资源；不要将浏览器直接 GET 的结果当成 MCP 验收。

| 现象 | 检查项 |
| --- | --- |
| Windows 找不到 `wsl.exe` 或发行版 | WSL 安装状态、`wsl.exe --list --verbose` 和 Host 的启动环境 |
| Ubuntu 内 doctor 成功，Windows 启动失败 | 发行版默认用户、启动入口路径、虚拟环境；不要依赖 shell 启动脚本输出或激活 |
| 能连接但看不到预期 session | Windows Host 与 HTTP 服务是否使用同一发行版、同一 Linux 用户及 zellij 环境 |
| stdio 启动后一直等待 | 等待 Host 输入属于正常现象；用 doctor 检查，不向协议 stdout 打印提示 |
| WSL 内服务可用，其他机器连不上 | NAT 目标 IP、Windows 监听地址、网络配置文件和防火墙；检查 `Get-Service iphlpsvc` 是否运行；若 WSL 内另有防火墙，也要允许 Windows 转发流量 |
| 重启 Windows/WSL 后失联 | 服务是否重新启动、NAT 内部 IP 是否变化、Windows 是否进入睡眠 |
| HTTP `403` | `--allowed-host` 是否匹配客户端实际访问的 Windows/DNS 地址和外部端口；有 Origin 时检查其白名单 |
| HTTP `401` 或 TLS 失败 | 复用安装指南中的 token、证书链与名称匹配检查 |

本页是部署与验收步骤，不能代替目标 Windows/WSL2、Host 和网络上的实际验证。

## 参考

- [微软：安装 WSL](https://learn.microsoft.com/en-us/windows/wsl/install)
- [微软：WSL 网络与端口转发](https://learn.microsoft.com/en-us/windows/wsl/networking)
- [微软：WSL 中的 systemd](https://learn.microsoft.com/en-us/windows/wsl/systemd)
- [OpenCode：本机 MCP 配置](https://opencode.ai/docs/mcp-servers/#local)
- [OpenCode：配置文件](https://opencode.ai/docs/config/)
- Codex CLI：`codex mcp add --help`、`codex mcp --help`；进一步说明见 [OpenAI 官方 MCP 文档](https://developers.openai.com/codex/mcp/)。
