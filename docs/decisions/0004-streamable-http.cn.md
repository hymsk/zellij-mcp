# ADR 0004：可配置监听的 Streamable HTTP/HTTPS

[中文](0004-streamable-http.cn.md) | [English](0004-streamable-http.md)

## 背景

stdio 要求 Host 启动本地子进程。HTTP MCP 客户端需要以 URL 连接独立运行的服务，同时项目仍需保持 Python 3.7+、无第三方运行时依赖以及现有 11 个工具的安全语义。

## 决策

- 保留默认 `serve` stdio 行为，显式选择 Streamable HTTP。
- 使用标准库实现 HTTP transport，复用现有 JSON-RPC 与工具运行时。
- 单一 `/mcp` 端点接受 POST，采用规范允许的 `application/json` 响应，不实现 SSE；GET 返回 405。
- 默认监听 `127.0.0.1`，也允许用户显式绑定 IPv4/IPv6 literal，包括 `0.0.0.0`/`::`；不解析 hostname，避免启动时 DNS 漂移。
- 始终强制 Bearer token。非 loopback listener 必须至少配置一个 `--allowed-host`；若请求存在 Origin，则必须精确命中 `--allowed-origin`。wildcard bind 不等价于 wildcard HTTP authority。
- `--allowed-host` 可写 `hostname`、IPv4、`[IPv6]`，并可带端口；带端口时精确匹配，不带端口时匹配当前 server bind port，从而支持显式的隧道/端口映射 authority。
- `--allowed-origin` 是绝对 `http://` 或 `https://` origin，只允许空路径或 `/`，并按 scheme、规范化 host 和有效端口精确匹配。没有 Origin 的非浏览器 MCP 客户端不需要配置 Origin。
- 通过成对 `--tls-cert` 与 `--tls-key` 提供原生 HTTPS，标准库 `SSLContext` server 最低 TLS 1.2。不输出证书/密钥路径或内容到网络响应；token 从环境变量读取，不接受命令行明文 token。
- 限制请求大小、读取等待与并发资源。工具的关闭保护、输入校验及结果不确定时的拒绝策略保持不变。
- 明文非 loopback HTTP 可用于用户明确选择的可信私网，CLI 会向 stderr 警告并推荐 HTTPS，但不禁止启动。本服务不需要反向代理，也不实现 OAuth、旧 HTTP+SSE 或多租户权限隔离。

## 权衡

JSON 响应满足当前请求/响应工具集，不需要为未使用的 server 推送维护 SSE 流。标准库实现避免提高 Python 最低版本或改变依赖策略，但必须自行测试 HTTP framing、认证和资源边界。

loopback 不是身份认证：同机进程和恶意网页仍是攻击面，因此认证与 Origin/Host 校验不能省略。非 loopback 扩大网络攻击面，因此要求用户同时声明可接受的 authority；HTTPS 保护传输但不替代 Bearer token 或 zellij 权限边界。认证成功的客户端拥有同一操作系统用户的终端操作权限，不能把 MCP session 当作用户隔离。

## 参考

- [MCP Streamable HTTP 规范（2025-11-25）](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [安装与 Host 集成](../guides/installation.cn.md)
