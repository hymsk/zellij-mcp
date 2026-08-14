# ADR 0004: Configurable Streamable HTTP/HTTPS

[中文](0004-streamable-http.cn.md) | [English](0004-streamable-http.md)

## Context

stdio requires a Host to start a local subprocess. HTTP clients need to connect to an independently running service by URL while preserving Python 3.7+, zero third-party runtime dependencies, and the safety semantics of the existing 11 tools.

## Decision

- Preserve default stdio behavior and make Streamable HTTP explicit.
- Implement HTTP with the standard library, reusing JSON-RPC and the tool runtime.
- Use a single `/mcp` endpoint with POST and specification-permitted `application/json` responses. Do not implement SSE; GET returns 405.
- Bind to `127.0.0.1` by default. Allow explicit IPv4/IPv6 literals, including `0.0.0.0` and `::`, without hostname resolution at startup.
- Always require a Bearer token. Non-loopback listeners require at least one `--allowed-host`. Origins, when present, must pass validation. Wildcard binding does not grant wildcard HTTP authority.
- `--allowed-host` accepts hostnames, IPv4, or bracketed IPv6 with an optional port. An explicit port must match exactly; an omitted port uses the listener port, supporting explicit tunnel and forwarding authorities.
- `--allowed-origin` is an absolute HTTP(S) origin with only an empty path or `/`. Match scheme, normalized host, and effective port. Non-browser clients without Origin do not need an Origin entry.
- Paired `--tls-cert` and `--tls-key` options enable native HTTPS using standard-library `SSLContext` with TLS 1.2+. Do not expose certificate/key paths or contents in network responses. Read the token from the environment, not a command-line argument.
- Bound request sizes, read waits, and concurrency. Preserve close protection, input validation, and rejection of uncertain outcomes.
- Plain non-loopback HTTP is allowed for explicitly chosen trusted private networks, with a stderr warning recommending HTTPS. No reverse proxy is required. OAuth, legacy HTTP+SSE, and tenant isolation are not provided.

## Tradeoffs

JSON responses cover the current request/response tool set without maintaining unused server-push streams. Standard-library HTTP preserves the Python floor and dependency policy but requires direct testing of framing, authentication, and resource bounds.

Loopback is not authentication: local processes and malicious websites remain relevant, so Bearer and Host/Origin checks remain required. HTTPS protects transport but does not replace authentication or zellij permissions. All authenticated clients share the operating system user's terminal access; MCP sessions are not user isolation.

## References

- [MCP Streamable HTTP specification (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [Installation and Host integration](../guides/installation.md)
