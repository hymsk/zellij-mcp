# zellij-mcp

> Zellij-MCP lets AI manage zellij sessions, tabs, and terminal panes on local or remote machines through MCP, running commands, inspecting output, and interacting with terminal programs.

[中文](README.cn.md) | [English](README.md) · [Documentation](docs/README.md) · [Specification (Chinese)](SPEC.md) · [Security policy](SECURITY.md) · [Contributing](CONTRIBUTING.md)

## Use cases

- **Ongoing interaction**: Let AI work repeatedly within the same GDB, Python REPL, or database CLI session, preserving context. It can even operate another harness to test runtimes or plugins in a real execution environment.
- **Remote background tasks**: Run builds, tests, or services in separate panes, letting AI check progress and logs and continue operations as needed.
- **Sensitive input**: Have AI create a dedicated Tab and start a program with input echo disabled, then enter a key or token directly in the terminal. Once the program receives it, AI can continue driving the program to use those credentials for authentication or configuration, without you pasting them into the conversation.

Zellij-MCP does not automatically monitor tasks or redact sensitive data. Hidden input is implemented by the program inside the pane, not by a dedicated credential-capture interface. Disabling echo does not make a value private from AI: if the program outputs credentials and AI reads them, they still enter the model context.

## Installation and connection

Choose **local use** or **remote use** based on where the terminals run. An MCP Host is the AI client that uses these tools, such as OpenCode.

Each setup section starts with a prompt you can send directly to AI. Replace the bracketed placeholders with your details; do not include real tokens or other credentials in the prompt.

| Mode | Use case | What you need |
| --- | --- | --- |
| [Local use](#local-use) | Let AI operate terminals on the current machine | Install zellij and Zellij-MCP locally; the Host starts the server over stdio |
| [Remote use](#remote-use) | Let AI operate terminals on a remote machine | Deploy the server on the target machine, then connect the Host using a URL and token; if a server already exists, configure only the client |

### Local use

**One prompt for AI-assisted setup:**

```text
Clone https://github.com/hymsk/zellij-mcp.git (reuse an existing checkout and preserve local changes), follow “Local use” in README.md and docs/guides/installation.md to install zellij and Zellij-MCP on my [operating system], configure a local stdio connection for [MCP Host name], and verify that it works; do not enable a network listener, preserve other configuration, and ask me for any missing information.
```

Requirements: Linux, Python 3.7+ with pip and venv support, Git, and zellij on `PATH`. On Windows, run the server inside [WSL2](docs/guides/windows.md); native Windows is not supported.

First [install zellij](docs/guides/installation.md#install-zellij), then install Zellij-MCP in a virtual environment:

```bash
git clone https://github.com/hymsk/zellij-mcp.git
cd zellij-mcp
python3 -m venv --copies .venv
. .venv/bin/activate
python3 -m pip install .
zellij-mcp doctor --json
```

`doctor` checks actual zellij capabilities, not just its version. Follow its `warnings` and `fixes` before connecting. Run `zellij-mcp version --json` to identify the installed build.

Register a local stdio server in your Host. The command and arguments to launch are:

```json
{
  "command": "/absolute/path/to/zellij-mcp/.venv/bin/zellij-mcp",
  "args": ["serve"]
}
```

Replace the example path with your actual installation path. These are illustrative launch fields, not a complete configuration for every Host; use your Host's field format, configuration location, and reload procedure. Ensure the server process launched by the Host can find zellij on `PATH`.

The Host starts the local stdio server. It does not listen on a network port or require an HTTP token. No separate HTTP service is needed, and `serve` reserves stdout for MCP JSON-RPC.

### Remote use

Remote use has two parts: deploying the server and connecting the client. The server runs on the machine whose terminals you want to operate; clients access it through Streamable HTTP/HTTPS. If a server is already available, skip to [Connect to the server](#connect-to-the-server). The client does not need zellij or Zellij-MCP installed.

#### Deploy the server

**One prompt for AI-assisted deployment:**

```text
Clone https://github.com/hymsk/zellij-mcp.git on [target server and operating system] (reuse an existing checkout and preserve local changes), follow “Deploy the server” in README.md and docs/guides/installation.md to install and deploy Zellij-MCP using a least-privilege account, a Bearer token, and HTTPS or a secure tunnel; confirm the listening address and permitted access before configuring and verifying the service, inject credentials securely without echoing them, preserve unrelated configuration, and ask me for any missing information.
```

On **the machine whose terminals you want to operate**, follow the installation steps under [Local use](#local-use) to install zellij and Zellij-MCP and run `doctor`. You do not need to configure a local Host. Then start a standalone Streamable HTTP/HTTPS service.

**Configure a token first.** HTTP mode requires the server environment variable `ZELLIJ_MCP_HTTP_TOKEN`, even when listening only on loopback. Generate and store a high-entropy random value using a password manager, such as a 64-character hexadecimal string. Valid tokens contain 32–512 ASCII Bearer characters; see the [authentication details](docs/guides/installation.md#streamable-http-connection) for the exact format.

For an interactive trial, enter an existing token in Bash with input echo disabled so its value is not written to command history:

```bash
read -r -s -p 'MCP token: ' ZELLIJ_MCP_HTTP_TOKEN
printf '\n'
export ZELLIJ_MCP_HTTP_TOKEN
```

**Prefer HTTPS for direct remote access.** Prepare a certificate trusted by your clients and its private key, then start the server with the installation environment activated:

```bash
zellij-mcp serve --transport streamable-http \
  --host 0.0.0.0 --port 8765 \
  --allowed-host mcp.example.com:8765 \
  --tls-cert /secure/config/server-chain.pem \
  --tls-key /secure/config/server-key.pem
```

Replace `mcp.example.com` and the certificate paths with your actual values. Clients connect to `https://mcp.example.com:8765/mcp`. The domain must resolve to the server, the certificate must cover that domain, and clients must trust the certificate chain. For a private CA, configure client trust instead of disabling certificate verification.

Before deploying, verify the following:

- **A token grants terminal access.** Authorized clients can execute commands, read terminal contents, and send input with the permissions of the operating system user running the server. This is not a sandbox and provides no tenant isolation. Use a dedicated, least-privilege account rather than root.
- **Restrict network access.** `0.0.0.0` listens on all IPv4 interfaces; replace it with a specific IP if appropriate. Allow only trusted clients through the firewall. Do not expose plaintext HTTP to the public internet or untrusted networks.
- **The Host allowlist is not a client IP allowlist.** `--allowed-host` specifies the server domain and port used in the client's URL. If the client sends an `Origin`, explicitly allow that origin with `--allowed-origin`; do not bypass validation.
- **Protect credentials.** Never put real tokens in READMEs, JSON configuration, URLs, command-line arguments, or logs. Use a separate token for each server and share it with clients through a secure channel. If it leaks, replace it, restart the service, and update the clients.

Without an HTTPS certificate, you can listen only on `127.0.0.1` and connect through an [SSH tunnel](docs/guides/installation.md#remote-access-and-security-boundaries); a Bearer token is still required. The commands above run in the foreground for testing. For long-term operation, configure service management, credential injection, and certificate maintenance separately.

#### Connect to the server

**One prompt for AI-assisted connection:**

```text
Read “Connect to the server” in README.md and docs/guides/installation.md at https://github.com/hymsk/zellij-mcp, configure a Streamable HTTP connection to [service URL] in my [MCP Host name], securely inject the Bearer token provided by the server, preserve TLS verification and other configuration, and verify the connection and target machine identity; do not clone the repository, install zellij or Zellij-MCP on the client, or modify the remote service, and ask me for any missing information.
```

If you or an administrator has already deployed the service, the client needs only an MCP Host supporting **Streamable HTTP**, not Python, zellij, or Zellij-MCP. Obtain the following from the server administrator:

- The service URL, such as `https://mcp.example.com:8765/mcp`, including the `/mcp` path.
- The corresponding Bearer token, obtained and stored securely.
- Client trust configuration for a private CA, if used, rather than disabling TLS verification.

For OpenCode, merge the following entry into your existing configuration without overwriting other settings:

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

Replace the URL and securely set `ZELLIJ_REMOTE_TOKEN` before launching OpenCode so the process inherits it. **Its value must match the server's `ZELLIJ_MCP_HTTP_TOKEN`**; the variable names may differ, but do not generate a different token on the client. The service uses Bearer authentication rather than OAuth, so set `oauth: false`.

For other Hosts, use their remote MCP configuration format, select Streamable HTTP, and provide `Authorization: Bearer <token>`. Do not use the local stdio `command`/`args` configuration or the legacy HTTP+SSE transport.

After connecting, call `zellij_mcp_doctor` and `workspace_list` to confirm that the discovered resources belong to the intended server. Give multiple connections distinct names and their own tokens; do not reuse resource IDs across services. See the [remote connection guide](docs/guides/installation.md#abc-servers-and-client-d) for multi-machine setup and troubleshooting `401`, `403`, TLS, and other issues.

## Uninstall

**One prompt for AI-assisted removal:** Fill in the scope you want to remove.

```text
Follow “Uninstall” in README.md at https://github.com/hymsk/zellij-mcp to remove [local installation / server / remote connection only] from [target machine / MCP Host], first confirm the installation and configuration locations, clean up only the selected scope and verify the result, preserve other configuration, zellij, and running tasks, and ask me before deleting source files or credentials.
```

Choose the procedure for your installation:

| Removal scope | Procedure |
| --- | --- |
| Local installation | Remove the corresponding MCP entry from the Host and reload it, confirm that the local MCP process has stopped, then uninstall the package |
| Server | Stop the corresponding HTTP/HTTPS service; if a service manager is configured, disable its automatic startup as well, then uninstall the package on the server |
| Remote connection only | Remove the corresponding connection from the Host and reload it; do not stop or uninstall the remote service |

To uninstall the package, run this in **the original installation environment**:

```bash
python3 -m pip uninstall zellij-mcp
```

Uninstalling the package does not close zellij sessions or stop commands in their panes. Source files, virtual environments, credentials, certificates, and any firewall rules or tunnels configured for the service are not automatically removed with the package. Clean them up separately after confirming they are no longer needed, taking care not to affect shared resources.

## Tools at a glance

| Tool | Purpose |
| --- | --- |
| `zellij_mcp_doctor` | Check the runtime environment, zellij capabilities, and server-side context |
| `workspace_create` | Create a session, Tab, or pane and run the specified command |
| `workspace_list` | Discover existing sessions and panes, distinguishing terminal and plugin panes |
| `tab_list` | List Tab IDs, active state, and pane membership |
| `tab_focus` | Switch to the specified Tab |
| `tab_rename` | Rename a Tab |
| `tab_close` | Close a Tab; requires an explicit `force=true` |
| `pane_write_text` | Send text to a terminal pane |
| `pane_send_key` | Send one supported key to a terminal pane |
| `pane_screen` | Read the current screen or available scrollback, optionally retaining ANSI escape sequences |
| `pane_close` | Close a terminal pane; requires an explicit `force=true` |

Stdio and HTTP/HTTPS provide the same 11 tools. Resource IDs come from discovery and must be used with their service and session. See the [tool reference](docs/reference/mcp-tools.md) for parameters, results, and limits.

## Development and contributing

Activate a development virtual environment in the source directory, then run:

```bash
python3 -m pip install -e ".[dev]"
make verify
```

`make verify` runs static checks, compilation, unit tests, and documentation checks. Real zellij integration tests run separately and create and close terminal resources; see the [testing documentation](docs/testing/README.md).

Read [Contributing](CONTRIBUTING.md) before submitting changes. The [specification (maintained only in Chinese)](SPEC.md) defines public behavior.

## License

[AGPL-3.0-or-later](LICENSE).
