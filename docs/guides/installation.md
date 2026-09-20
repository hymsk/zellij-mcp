# Installation and Host Integration

[中文](installation.cn.md) | [English](installation.md)

See the [Windows/WSL2 guide](windows.md) for local Windows operation and external service deployment, including local MCP setup through `wsl.exe`, Windows port forwarding, and firewall configuration.

## Prerequisites

`zellij-mcp` supports Linux, Python 3.7+, and zellij. zellij must be on `PATH` and support:

- Background session creation through `attach --create-background`.
- Stable Tab operations: `list-tabs`, `new-tab`, `go-to-tab-by-id`, `rename-tab-by-id`, and `close-tab-by-id`.
- Direct pane I/O by pane ID through `write-chars`, `send-keys`, and `dump-screen`.

These capabilities vary across zellij releases. Run `doctor` in the actual environment after installation instead of relying on the version number alone.

## Install zellij

Follow this order: install zellij → configure `PATH` → install the MCP runtime package → run `doctor` → configure the Host. Install zellij on the machine running the MCP service. Remote clients do not need it unless they also run a local MCP service.

### Official prebuilt binary

This Bash example pins the official [v0.45.1 release](https://github.com/zellij-org/zellij/releases/tag/v0.45.1) for Linux where `uname -m` returns `x86_64` or `aarch64`. It requires `curl`, `tar`, and GNU coreutils (including `sha256sum`, `install`, and `cut`). Run as the same user that starts MCP. It installs to `~/.local/bin/zellij` without sudo. If a compatible version is already installed, skip the download and retain the version and capability checks.

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

The release's `.sha256sum` checks the extracted `zellij` binary, not the `.tar.gz`. The example extracts the digest and verifies it against the local filename. Download or verification failure stops the parenthesized steps before installation. The temporary download directory is removed automatically.

`export PATH` affects only the current shell. Add it to the shell configuration used to launch the Host, such as `~/.bashrc`, then open a new terminal. If MCP starts through a desktop application or service manager, configure that process's `PATH` to include `~/.local/bin` too. An absolute MCP command path alone does not let its subprocesses find zellij.

### Other installation methods and upgrades

For other architectures, see the [official zellij installation documentation](https://zellij.dev/documentation/installation.html). With a Rust toolchain that meets zellij's requirements, you can also build from source:

```bash
cargo install --locked zellij --version 0.45.1
export PATH="$HOME/.cargo/bin:$PATH"
zellij --version
```

Distribution repositories may provide older versions. Run this project's `doctor` even after installation through a system package manager. For upgrades, adjust the example version and confirm that the corresponding release assets exist. If multiple zellij binaries are installed, use `command -v zellij` to check the path used in the MCP startup environment. Successful `zellij --version` output only proves that the binary runs, not that every required MCP capability is available.

## Install the runtime package

From the repository root:

```bash
python3 -m pip install .
zellij-mcp version
zellij-mcp doctor --json
```

If `doctor` exits nonzero, follow its `warnings` and `fixes` to install or upgrade zellij before configuring the server in an MCP Host.

Development installation includes testing, coverage, type checking, lint, and security tools:

```bash
python3 -m pip install -e ".[dev]"
```

## Configure an MCP Host

Any MCP Host supporting local stdio transport should start:

```text
zellij-mcp serve
```

The corresponding command and args are:

```json
{
  "command": "zellij-mcp",
  "args": ["serve"]
}
```

Place these fields in the Host's MCP server configuration. Configuration format, file location, and reload behavior are outside this project's interface; consult the documentation for your Host.

For a virtual environment, use the absolute path to its `zellij-mcp`, for example:

```json
{
  "command": "/absolute/path/to/.venv/bin/zellij-mcp",
  "args": ["serve"]
}
```

Do not configure `command` as a shell string or write logs or ordinary text to `serve` stdout. The server's stdout is the MCP JSON-RPC channel.

## Streamable HTTP connection

`zellij-mcp serve` still defaults to stdio. To connect by URL, start the HTTP service separately:

```bash
# Set ZELLIJ_MCP_HTTP_TOKEN securely; keep real values out of shell history and the repository.
zellij-mcp serve --transport streamable-http --host 127.0.0.1 --port 8765
```

The required environment variable `ZELLIJ_MCP_HTTP_TOKEN` provides a Bearer token of 32–512 ASCII Bearer characters (letters, digits, `-._~+/`, and optional trailing `=`). Use a high-entropy random value from a password manager. Clients must send `Authorization: Bearer <token>`. The token is not an MCP session ID and does not isolate resource authorization between clients.

Select **Streamable HTTP** in the client, use `http://127.0.0.1:8765/mcp`, and supply the authentication header through the Host's secure configuration mechanism. HTTP does not use the stdio `command`/`args` registration structure. Any trusted A/B/C node can run the service, and D can connect directly by URL without a reverse proxy. URL, headers, and environment interpolation fields depend on the Host; do not copy another Host's configuration format blindly.

### HTTP protocol behavior

- `POST /mcp` accepts one UTF-8 JSON-RPC object. Headers must include `Content-Type: application/json` and `Accept` supporting both `application/json` and `text/event-stream`.
- Requests return JSON; accepted notifications and client responses return an empty `202`. `GET /mcp` returns `405`; no SSE or legacy HTTP+SSE endpoint is provided.
- Negotiable versions are `2025-03-26`, `2025-06-18`, and `2025-11-25`. Send `notifications/initialized` after initialization, then include the negotiated `MCP-Protocol-Version` and the initialization response's `MCP-Session-Id` in subsequent requests.
- `DELETE /mcp` ends the MCP session without closing zellij resources it created. Reinitialize after MCP session idle expiry or server restart.
- Limits are 64 MCP sessions, a 30-minute idle TTL, 16 concurrent connections, 1 MiB each for requests and responses, and a 5-second socket read timeout. Each response closes the HTTP connection; request headers maintain the MCP session.
- Each MCP session has its own tool runtime and creation request cache. Deduplication does not span sessions, expiry, or process restart. If an outcome is uncertain, discover and verify existing resources before acting; do not simply reinitialize and replay creation.

### Remote access and security boundaries

`--host` defaults to `127.0.0.1` and also accepts explicit IPv4/IPv6 literals such as `192.0.2.10`, `0.0.0.0`, `::1`, and `::`. Hostnames are not accepted. `0.0.0.0`/`::` control socket binding only; they do not automatically accept arbitrary `Host` or `Origin` values. HTTP operates zellij resources accessible to the server's startup user, not the client's local terminal.

Every non-loopback listener requires at least one `--allowed-host`; repeat the option for additional entries:

- Entries can be ASCII hostnames, IPv4 addresses, or bracketed IPv6 addresses, optionally with a port, such as `mcp.internal:9443`, `192.0.2.10:8765`, or `[2001:db8::10]:8765`.
- With an explicit port, the request's `Host` must match that port exactly. Without one, it matches the server's actual bind port. This allows explicitly mapped client/tunnel ports without widening authority checks for wildcard binding.
- `--allowed-origin` is a repeatable absolute `http://` or `https://` origin. Scheme, normalized host, and effective port must match exactly; the path must be empty or `/`. Non-browser MCP clients without `Origin` do not need this option. Requests carrying `Origin` receive `403` unless an allowlist entry matches.

Native HTTPS is recommended and does not require a proxy:

```bash
zellij-mcp serve --transport streamable-http \
  --host 0.0.0.0 --port 8765 \
  --allowed-host mcp.internal:8765 \
  --tls-cert /secure/config/server-chain.pem \
  --tls-key /secure/config/server-key.pem
```

Supply `--tls-cert` and `--tls-key` together, pointing to a PEM certificate chain and private key. The server uses TLS 1.2 or later. Private key contents are not printed, but file permissions and certificate issuance/rotation are the deployer's responsibility. Clients connect to `https://mcp.internal:8765/mcp` and still send the Bearer token.

If the user explicitly chooses plaintext HTTP on a trusted internal network:

```bash
zellij-mcp serve --transport streamable-http \
  --host 0.0.0.0 --port 8765 \
  --allowed-host mcp.internal:8765
```

The CLI warns on stderr that the listener has no TLS and recommends HTTPS; trusted private-network use is permitted. Do not expose a plaintext listener to the public Internet or untrusted networks.

A loopback listener can also be reached through a secure tunnel. Run this on the client to forward to server loopback:

```bash
ssh -N -T -L 127.0.0.1:8765:127.0.0.1:8765 user@server
```

The client continues using `http://127.0.0.1:8765/mcp` with a Bearer token. This forwards **HTTP MCP**; it does not change the MCP transport to SSH stdio. If the mapped client's `Host` port differs from the backend bind port, explicitly add the corresponding `--allowed-host host:port` to the server's startup arguments.

With default loopback and no explicit allowlists, request `Host` must match the actual loopback listener and bind port; any `Origin` must use the same scheme, host, and port. Configuring only `--allowed-origin` retains the listener IP/port as the default Host. Configuring `--allowed-host` uses that list for Host checks. Explicitly configuring either list disables automatic same-origin acceptance: requests carrying Origin must match an explicit `--allowed-origin` entry. Do not strip or rewrite an untrusted Origin to bypass validation. Browser access is limited to explicitly listed origins.

Remote calls should specify `session_name` explicitly. The HTTP server's zellij context comes from its startup process, not the client. Close protection still rejects incomplete identity conservatively; do not disable safeguards for remote use.

## A/B/C servers and client D

Replace these example addresses with actual internal IPs. Each A/B/C machine needs Linux, Python, compatible zellij, and this project's runtime. D only needs a Streamable HTTP MCP Host.

| Server | Example address | Connection name in D | Token environment variable in D |
| --- | --- | --- | --- |
| A | `192.168.1.10:8765` | `zellij-a` | `ZELLIJ_A_TOKEN` |
| B | `192.168.1.11:8765` | `zellij-b` | `ZELLIJ_B_TOKEN` |
| C | `192.168.1.12:8765` | `zellij-c` | `ZELLIJ_C_TOKEN` |

### Prepare each server

First [install zellij](#install-zellij) on each A/B/C machine and ensure the service process can find it on `PATH`. Then, from each source root, install in a virtual environment and check capabilities:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/zellij-mcp doctor --json
```

Generate and securely store a different random token for each A/B/C server, for example a 64-character hexadecimal value from a password manager. Every server uses the environment variable name `ZELLIJ_MCP_HTTP_TOKEN`; D stores the corresponding values in the three variables listed above. Never place real tokens in JSON, source code, or shell history.

For an interactive trial, read an existing token without echoing it in Bash:

```bash
read -r -s -p 'MCP token: ' ZELLIJ_MCP_HTTP_TOKEN
export ZELLIJ_MCP_HTTP_TOKEN
```

For trusted internal HTTP, start A as follows. On B/C, replace the IP in `--allowed-host`:

```bash
.venv/bin/zellij-mcp serve --transport streamable-http \
  --host 0.0.0.0 --port 8765 \
  --allowed-host 192.168.1.10:8765
```

`--allowed-host` specifies the **server address** in the client's URL, not D's source IP. Repeat it to allow both IP and DNS access. Configure source restrictions separately in the firewall, preferably allowing only D to reach TCP 8765. Do not expose the plaintext port to the public Internet. These commands run in the foreground; persistent operation requires separate service management and secure credential injection.

For recommended HTTPS, add paired `--tls-cert` and `--tls-key` arguments and change D's URLs to `https://`. The certificate SAN must match the domain or IP used by D, and D must trust the certificate chain. Configure client trust for a private CA; do not disable certificate verification. Restart the service after updating certificate files.

### Configure OpenCode on D

Merge the following `mcp` entries into D's OpenCode configuration without overwriting existing settings. This example uses internal HTTP; prefer certificate-backed HTTPS addresses for production:

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

Before starting OpenCode on D, ensure it inherits `ZELLIJ_A_TOKEN`, `ZELLIJ_B_TOKEN`, and `ZELLIJ_C_TOKEN`. This service uses a fixed Bearer token and has no OAuth, so set `oauth: false` explicitly. See the [official MCP documentation](https://opencode.ai/docs/mcp-servers/) for OpenCode remote configuration and environment interpolation. Other Hosts use their respective remote URL and authentication settings.

### Verification and troubleshooting

1. Run `opencode mcp list` on D to check all three connections.
2. Call doctor and `workspace_list` separately through `zellij-a`, `zellij-b`, and `zellij-c`, confirming that each result belongs to the correct machine.
3. Each service returns 11 tools. Resource references must retain the server name along with `session_name` and `pane_id`/`tab_id`; do not reuse IDs across services.

| Symptom | Check |
| --- | --- |
| Connection refused or timeout | Service process, bind address, port, firewall, and route from D to the server |
| `401` | Whether the Host inherited D's environment variables and whether the token matches the corresponding server |
| `403` | Whether the URL's server address/port matches `--allowed-host`, and any Origin matches its allowlist |
| `400` | Client protocol version, session header, or request format; use a compatible MCP client |
| `404` | The URL must include `/mcp`; reinitialize expired sessions |
| Browser GET returns `405` | Expected: the endpoint uses POST JSON and provides neither a browser page nor SSE GET |
| TLS verification failure | URL versus certificate SAN, expiry, complete certificate chain, and client CA trust |
| Rejected zellij operation | Server user permissions, doctor capabilities, and current pane protection; do not bypass safeguards |

This configuration example does not establish real cross-machine acceptance; verify it in the target network before deployment. All three tokens allow command execution as their respective server users. Use restricted accounts and grant access only to trusted clients.

## Check the connection

After connecting the Host, call `zellij_mcp_doctor`. Confirm that the capabilities needed for the workflow are available:

- `zellij`.
- `zellij_stable_tab_control`.
- `zellij_direct_pane_io`.

Call `workspace_list` or `tab_list` to confirm visible resources before creating, writing, reading, or closing panes and Tabs. See the [MCP tools reference](../reference/mcp-tools.md) for all parameters.

## Context and permissions

At startup, the server recovers allowlisted zellij environment variables from ancestor processes belonging to the same Linux user to identify the current session and pane. If that context cannot be recovered, discovery and close protection remain conservative.

The server inherits the operating system permissions of its startup user. Configure it only for trusted Hosts: `workspace_create` can execute argv commands, and pane write tools can send input to terminal programs.
