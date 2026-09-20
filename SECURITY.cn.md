# 安全政策

[中文](SECURITY.cn.md) | [English](SECURITY.md)

## 报告安全问题

安全问题请使用 GitHub Private Vulnerability Reporting。不要在公开 Issue 中提交 Host 配置、session dump、终端屏幕内容、命令历史或凭据。

## 安全边界

- server 以启动它的操作系统用户身份操作 zellij。
- `workspace_create` 会直接执行调用方提供的 argv command。
- pane 写入和按键发送会影响目标终端内程序。
- 关闭操作要求 `force=true`，并保护当前 MCP pane 和 plugin pane。
- 只应将 server 配置给受信任的 MCP Host 和工作流。
- Streamable HTTP 默认监听 loopback，也允许用户显式监听具体 IPv4/IPv6 或 wildcard；非 loopback 必须配置 Host 白名单。Bearer token 始终必需，认证不是多租户授权，所有获准客户端拥有同一操作系统用户的终端访问范围。
- 存在 `Origin` 时必须严格命中配置的 Origin 白名单；监听 `0.0.0.0`/`::` 不会自动接受任意 Host 或 Origin。不要使用通配 Host/Origin 绕过边界。
- 跨主机访问推荐使用原生 HTTPS（TLS 1.2+）或安全隧道。明文非 loopback HTTP 仅限可信私网；不得在 URL、日志、命令行参数或仓库中记录 token 或 private key。
