# Local MCP Setup and Service Deployment on Windows

[中文](windows.cn.md) | [English](windows.md)

This guide covers Windows-specific deployment: run zellij and MCP in WSL2, have a Windows Host launch local stdio through `wsl.exe`, or expose the WSL2 HTTP/HTTPS service to other machines. Remote client configuration uses the shared [installation guide](installation.md#streamable-http-connection).

The runtime baseline is Linux. On Windows, deploy in WSL2's Linux environment; native Windows Python combined with `zellij.exe` is not a supported configuration. The examples use the distribution name `Ubuntu`; replace it throughout if yours differs.

| Usage | Service process | Windows configuration |
| --- | --- | --- |
| Windows Host using local zellij | Host starts stdio MCP in WSL2 through `wsl.exe` | Local MCP launch command; no listening port |
| Other machines accessing a Windows-hosted service | Independent HTTP/HTTPS MCP in WSL2 | WSL listener, Windows network entry point, and firewall |

## 1. Prepare WSL2

Use Windows 11 or Windows 10 version 2004 / Build 19041 or later with `wsl --install` support. Install in **administrator PowerShell**; skip installation if WSL2 and the target distribution already exist:

```powershell
wsl.exe --install -d Ubuntu
```

Restart Windows as prompted, then complete Linux user initialization when first opening Ubuntu. Check from PowerShell:

```powershell
wsl.exe --update
wsl.exe --list --verbose
```

Confirm that Ubuntu's `VERSION` is `2`. If it is still `1`, save work in the distribution, then run `wsl.exe --set-version Ubuntu 2`. Enter Ubuntu:

```powershell
wsl.exe --distribution Ubuntu
```

All subsequent Bash commands run inside Ubuntu; PowerShell commands run on Windows.

### Install zellij and MCP

Prepare dependencies in Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip curl ca-certificates tar coreutils git
```

First [install the Linux version of zellij](installation.md#install-zellij) and configure `PATH`. Then install MCP into that Linux user's virtual environment. If source is already checked out, use that directory and skip cloning:

```bash
mkdir -p "$HOME/src"
git clone https://github.com/hymsk/zellij-mcp.git "$HOME/src/zellij-mcp"
python3 -m venv "$HOME/.local/share/zellij-mcp/venv"
"$HOME/.local/share/zellij-mcp/venv/bin/python" -m pip install "$HOME/src/zellij-mcp"
"$HOME/.local/share/zellij-mcp/venv/bin/zellij-mcp" doctor --json
```

If `doctor` exits nonzero, resolve zellij path or capability issues before configuring the Host. The local Windows Host and external service should use the same distribution and Linux user to operate the same zellij resources.

### Create a launcher independent of interactive shells

A Windows Host launching `wsl.exe` should not depend on `.bashrc` to activate a virtual environment. This launcher sets the zellij search path explicitly and starts MCP directly from the virtual environment without printing extra text to stdout.

Run in Ubuntu:

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

Back in Windows PowerShell, check through the entry point the Host will use:

```powershell
wsl.exe --distribution Ubuntu --exec /usr/local/bin/zellij-mcp-wsl doctor --json
```

Configure stdio after this succeeds. Do not manually start `serve` to decide whether it is stuck: it waits for MCP requests from the Host on stdin.

## 2. Configure local MCP on Windows

This section applies when the Host process runs on Windows and the service runs in WSL2. If the Host itself runs in WSL2, use the [Linux stdio configuration](installation.md#configure-an-mcp-host).

### OpenCode

Edit the Windows user's `%USERPROFILE%\.config\opencode\opencode.json`, or the file specified by `OPENCODE_CONFIG` if set. Merge the following entry into the existing `mcp` object without overwriting other settings:

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

Restart OpenCode and run `opencode mcp list` in PowerShell to check the connection. To pin the Linux user, add `--user` and the actual username before `--exec`. Avoid accidentally starting a separate set of zellij resources as root.

### Codex CLI

Register the same stdio entry point in Windows PowerShell:

```powershell
codex mcp add zellij-wsl -- wsl.exe --distribution Ubuntu --exec /usr/local/bin/zellij-mcp-wsl serve
codex mcp list
```

First confirm that the installed version's `codex mcp add --help` supports the `-- <COMMAND>...` form. The CLI uses its current user's configuration. Codex running on Windows and Codex running inside WSL are different process environments; registration inside WSL does not complete Windows configuration. Inspect and edit an existing entry if the name is already registered.

After restarting the Host, call `zellij_mcp_doctor` and `workspace_list`. Confirm discovery of 11 tools and resources belonging to the intended WSL distribution and Linux user. A configuration entry alone does not prove that the MCP handshake or resource operations passed.

## 3. Start an externally accessible service in WSL2

External access requires a separate HTTP/HTTPS process. Local stdio stdin/stdout cannot be mapped directly to a TCP port. Client URLs, Bearer authentication, and MCP protocol requirements are documented in the shared [installation guide](installation.md#streamable-http-connection).

The examples use Windows LAN address `192.168.1.20`, port `8765`, and allowed client address `192.168.1.50`. Replace them with your actual addresses.

In Ubuntu, read an existing high-entropy token without echoing it, then start the service:

```bash
read -r -s -p 'MCP token: ' ZELLIJ_MCP_HTTP_TOKEN
export ZELLIJ_MCP_HTTP_TOKEN
/usr/local/bin/zellij-mcp-wsl serve --transport streamable-http \
  --host 0.0.0.0 --port 8765 \
  --allowed-host 192.168.1.20:8765
```

The token must use 32–512 ASCII Bearer characters as specified in the [installation guide](installation.md#streamable-http-connection). This HTTP example is for a trusted private network. Keep the terminal and WSL instance running until connectivity checks finish.

- `--host 0.0.0.0` accepts connections forwarded by Windows. Binding only to WSL `127.0.0.1` does not support NAT forwarding.
- Set `--allowed-host` to the Windows IP or DNS name and port in the client's URL. Do not use the client IP or automatically substitute the internal WSL address. Port forwarding preserves the HTTP Host header.
- To also test locally from Windows through `127.0.0.1`, add `--allowed-host 127.0.0.1:8765`.
- `workspace_create` executes Linux commands in WSL; `cwd` also uses Linux paths. Access Windows files through their corresponding `/mnt/c/...` paths.

### Enable HTTPS

For access across untrusted networks, obtain a trusted certificate for the DNS name clients will use and store the certificate chain and private key in WSL. This example assumes `mcp.example.com` and port `8765` on both Windows and WSL:

```bash
/usr/local/bin/zellij-mcp-wsl serve --transport streamable-http \
  --host 0.0.0.0 --port 8765 \
  --allowed-host mcp.example.com:8765 \
  --tls-cert "$HOME/.config/zellij-mcp/server-chain.pem" \
  --tls-key "$HOME/.config/zellij-mcp/server-key.pem"
```

Set `ZELLIJ_MCP_HTTP_TOKEN` first. The certificate SAN must contain the actual DNS name, and clients must trust the chain; `mcp.example.com` is only an example. Windows port forwarding passes TLS through, so Windows does not need to terminate HTTPS.

## 4. Expose the network entry point through Windows

### Default WSL2 NAT mode

Keep the service from section 3 running. In **administrator PowerShell**, set the actual addresses and obtain the WSL IPv4 address:

```powershell
$ZellijWindowsIp = "192.168.1.20"
$ZellijClientIp = "192.168.1.50"
$ZellijWslAddresses = wsl.exe --distribution Ubuntu --exec hostname -I
if ($LASTEXITCODE -ne 0) { throw "Could not query WSL addresses" }
$ZellijWslIp = ($ZellijWslAddresses -split '\s+' |
  Where-Object { $_ -match '^\d{1,3}(\.\d{1,3}){3}$' } |
  Select-Object -First 1)
if (-not $ZellijWslIp) { throw "No WSL IPv4 address found" }
$ZellijWslIp
```

Confirm the selected address belongs to Ubuntu's WSL network. With multiple interfaces, such as Docker networks, verify against `ip -4 addr show eth0` inside Ubuntu and set `$ZellijWslIp` manually if necessary. `hostname -I` uses an uppercase `I`.

Create TCP forwarding and an inbound rule for that client:

```powershell
netsh interface portproxy add v4tov4 listenaddress=$ZellijWindowsIp listenport=8765 connectaddress=$ZellijWslIp connectport=8765
New-NetFirewallRule -Name "ZellijMCP-8765" -DisplayName "Zellij MCP 8765" -Direction Inbound -Action Allow -Protocol TCP -LocalAddress $ZellijWindowsIp -LocalPort 8765 -RemoteAddress $ZellijClientIp -Profile Private
netsh interface portproxy show v4tov4
```

The example uses a trusted `Private` network profile. Check the actual profile with `Get-NetConnectionProfile`; adapt domain networks according to organizational policy. Do not disable the entire firewall to troubleshoot connectivity. `--allowed-host` validates the HTTP destination address; `-RemoteAddress` restricts the client source here.

WSL's internal IP may change after restart. Query it again and update only this service's forwarding entry:

```powershell
netsh interface portproxy set v4tov4 listenaddress=$ZellijWindowsIp listenport=8765 connectaddress=$ZellijWslIp connectport=8765
```

This command uses the refreshed variables. Do not recreate an existing firewall rule. If the Windows LAN address changes, also update the listening address, rule, and server `--allowed-host`.

### Windows 11 already using mirrored networking

Windows 11 22H2 and later support WSL `networkingMode=mirrored`. If already using that mode, access the service through mirrored networking and skip NAT `portproxy` steps. There is no need to change WSL's global network mode for this project.

Allow TCP 8765 in the Windows/Hyper-V firewall according to local policy. Microsoft's documentation gives this port-level Hyper-V rule, run in administrator PowerShell, without globally opening WSL inbound traffic:

```powershell
New-NetFirewallHyperVRule -Name "ZellijMCP-8765" -DisplayName "Zellij MCP 8765" -Direction Inbound -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -Protocol TCP -LocalPorts 8765
```

Client source scope should still be restricted by the actual Windows/Hyper-V network policy. See the [Microsoft WSL networking documentation](https://learn.microsoft.com/en-us/windows/wsl/networking#mirrored-mode-networking) for supported versions, configuration, and firewall requirements.

### Public or cross-subnet access

Windows forwarding alone does not configure routers, cloud security groups, or DNS. For direct access, separately establish routing/forwarding to the Windows listening address and port and use HTTPS, or use the shared [secure tunnel approach](installation.md#remote-access-and-security-boundaries). The external URL's DNS name and port must match `--allowed-host`, and the certificate must cover that DNS name. If public forwarding uses a different port, the allowlist must use that external port.

## 5. Persistent operation and shutdown

Exiting the foreground service stops MCP. Shutting down WSL, powering off Windows, or sleeping also affects availability. For process management, configure a user service in a WSL distribution with systemd enabled.

First confirm that the user service manager works with `systemctl --user status`. If systemd is not enabled, follow the [Microsoft systemd guide](https://learn.microsoft.com/en-us/windows/wsl/systemd), saving existing work before restarting WSL. The following remains a trusted private-network HTTP example.

In Ubuntu, create a private configuration directory, read the token without echoing, and write an environment file:

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

Save the following as `~/.config/systemd/user/zellij-mcp.service`, adapting startup arguments to the actual address. HTTPS deployments use the DNS allowlist and certificate arguments from section 3:

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

Stop any foreground instance occupying the same port before starting the user service:

```bash
systemctl --user daemon-reload
systemctl --user enable --now zellij-mcp.service
systemctl --user status zellij-mcp.service
journalctl --user -u zellij-mcp.service -n 50 --no-pager
```

`enable` applies to the user service manager inside WSL; it does not register a Windows startup service. Microsoft states that systemd services alone do not keep a WSL instance alive. After Windows restarts, start the distribution and user service again and check the NAT address. Continuous operation also requires suitable Windows startup and power policies.

Stop the user service and disable its startup:

```bash
systemctl --user disable --now zellij-mcp.service
```

To remove external access, delete only the rules created by this guide in administrator PowerShell, using the actual listening address configured earlier:

```powershell
netsh interface portproxy delete v4tov4 listenaddress=192.168.1.20 listenport=8765
Remove-NetFirewallRule -Name "ZellijMCP-8765"
```

If a mirrored-network Hyper-V rule was configured, separately run `Remove-NetFirewallHyperVRule -Name "ZellijMCP-8765"`. Do not remove rules that were never created or use `portproxy reset` to clear other services' forwarding. Stopping MCP does not automatically close existing zellij resources.

## 6. Verification and troubleshooting

1. Run `/usr/local/bin/zellij-mcp-wsl doctor --json` in Ubuntu to confirm the runtime environment.
2. Run doctor from Windows through the same `wsl.exe` command to confirm distribution, user, and paths; the Host subsequently discovers tools over local stdio.
3. After exposing the service, run `Test-NetConnection 192.168.1.20 -Port 8765` on the target client to check TCP reachability. This does not verify Bearer authentication, TLS, or the MCP handshake.
4. Use the [shared connection checks](installation.md#check-the-connection) to verify MCP initialization, 11 tools, and target resources. Direct browser GET results do not establish MCP acceptance.

| Symptom | Check |
| --- | --- |
| Windows cannot find `wsl.exe` or the distribution | WSL installation, `wsl.exe --list --verbose`, and Host startup environment |
| Doctor succeeds in Ubuntu but Windows launch fails | Distribution default user, launcher path, and virtual environment; do not rely on shell startup output or activation |
| Connected but expected sessions are missing | Whether the Windows Host and HTTP service use the same distribution, Linux user, and zellij environment |
| stdio keeps waiting after startup | Waiting for Host input is normal; use doctor for checks and do not print prompts to protocol stdout |
| Service works in WSL but other machines cannot connect | NAT target IP, Windows listening address, network profile, and firewall; check `Get-Service iphlpsvc`; if WSL has its own firewall, allow Windows forwarding traffic |
| Unreachable after Windows/WSL restart | Whether the service restarted, NAT's internal IP changed, or Windows entered sleep |
| HTTP `403` | Whether `--allowed-host` matches the actual Windows/DNS address and external port used by the client; check Origin's allowlist when present |
| HTTP `401` or TLS failure | Reuse the installation guide's token, certificate chain, and name matching checks |

This page provides deployment and acceptance steps; it does not replace verification on the target Windows/WSL2, Host, and network.

## References

- [Microsoft: Install WSL](https://learn.microsoft.com/en-us/windows/wsl/install)
- [Microsoft: WSL networking and port forwarding](https://learn.microsoft.com/en-us/windows/wsl/networking)
- [Microsoft: systemd in WSL](https://learn.microsoft.com/en-us/windows/wsl/systemd)
- [OpenCode: Local MCP configuration](https://opencode.ai/docs/mcp-servers/#local)
- [OpenCode: Configuration files](https://opencode.ai/docs/config/)
- Codex CLI: `codex mcp add --help`, `codex mcp --help`; see the [official OpenAI MCP documentation](https://developers.openai.com/codex/mcp/) for further information.
