# Security Policy

[中文](SECURITY.cn.md) | [English](SECURITY.md)

## Reporting

Report security issues through GitHub Private Vulnerability Reporting. Do not include Host configuration, session dumps, terminal screens, command history, or credentials in public issues.

## Security boundary

- The server operates zellij with the permissions of the operating system user who starts it.
- `workspace_create` directly executes caller-provided argv commands.
- Pane text and key input affect the program running in the target terminal.
- Close operations require `force=true` and protect the current MCP pane and plugin panes.
- Configure the server only for trusted MCP Hosts and workflows.
- Streamable HTTP binds to loopback by default and can explicitly bind to IPv4/IPv6 addresses or wildcards. Non-loopback listeners require a Host allowlist. Bearer authentication is always required; all authenticated clients have the same operating system user's terminal access. Authentication is not tenant isolation.
- Requests carrying an `Origin` must pass Origin validation. Binding to `0.0.0.0` or `::` does not accept arbitrary Host or Origin values. Do not bypass validation with wildcard authorities.
- Use native HTTPS (TLS 1.2+) or a secure tunnel for cross-machine access. Plain HTTP on non-loopback interfaces is limited to trusted private networks. Never put tokens or private keys in URLs, logs, command-line arguments, or the repository.
