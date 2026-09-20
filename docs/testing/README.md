# Testing Documentation

[中文](README.cn.md) | [English](README.md)

- [full-test-plan.md](full-test-plan.md): layered direct pane test plan and quality gates.
- [requirements-coverage.md](requirements-coverage.md): coverage matrix for all 32 requirements in the root [SPEC](../../SPEC.md), including the original 24 MVP requirements, HTTP/HTTPS, and public interface requirements.
- [test-cases.md](test-cases.md): cases for the 11 tools and safety boundaries.

## Acceptance priorities

- `tools/list` returns exactly 11 tools.
- Both source and installed `tools/list` return complete annotations and strict schemas.
- Initialize guidance covers explicit zellij requests, persistent interaction, background terminal tasks, configured remote access, and the fallback to normal Host execution tools, within 360 characters. Tool descriptions retain focus preservation, cleanup after verified completion, and retention exceptions; creation repeats the task selection cues within 420 characters. Every top-level parameter has a description; boolean and creation mode defaults match the runtime. Protocol smoke and quality tests verify these contracts.
- Tool and top-level parameter descriptions total at most 5200 characters, excluding initialization. Quality checks also cover inspection before input, newline/key side effects, completion evidence, close protection, retention, and creation retry constraints. This is a character budget, not a token count.
- `workspace_create` runs argv commands directly.
- `workspace_list` and `tab_list` return live resources and stable IDs.
- `pane_write_text` invokes `write-chars`; `pane_send_key` invokes restricted `send-keys`.
- `pane_screen` supports viewport, full, ANSI, and the 262144-character limit.
- `pane_close` and `tab_close` require `force=true` and protect special targets.
- MCP Hosts use the same discovery and I/O acceptance process.
- HTTP transport tests use real loopback sockets and mocked tools to verify handshake, 11 tools, session isolation, authentication, Origin/Host, framing, versions, and resource limits. Wildcard bind tests still access the listener only through loopback and do not operate user zellij resources.
- HTTPS cases generate short-lived self-signed certificate/key files in temporary directories, verify TLS 1.2+ handshake and Bearer authentication, and retain no files afterward.
- The installed wheel's `source_commit` matches the build checkout.
- Build-time version reading supports Python 3.7 string nodes without executing package initialization. Regular wheels, editable wheels, and prepared metadata include the complete English README long description and Markdown content type.
- Real pane/Tab lifecycle tests using an isolated `ZELLIJ_SOCKET_DIR` leave no sessions behind.
- For Windows/WSL2, follow the [Windows guide](../guides/windows.md#6-verification-and-troubleshooting) to separately verify doctor inside the distribution, local Windows stdio, NAT or mirrored network access, and HTTP/HTTPS handshakes. Linux unit tests do not establish acceptance for Windows scenarios.

## Commands

This project has no GitHub Actions CI. Run local checks appropriate to the changes; do not report unexecuted checks as passing.

```bash
make check
make verify
python3 -m pytest tests/unit/test_http_transport.py -q
make integration-smoke
make integration-installed
make integration-isolated
```

`integration-isolated` builds and installs a temporary wheel, isolates `HOME`, `XDG_*`, `ZELLIJ_CONFIG_DIR`, and `ZELLIJ_SOCKET_DIR`, and creates and cleans real zellij resources.

## Documentation checks

At minimum, verify:

- Each language's section README indexes its direct Markdown documents.
- Relative links and anchors exist, and body links stay in the same language. Introduction navigation on line 3, 5, or 7 allows the same-page language switch, not cross-language guide links; regression tests cover all three layouts.
- Except for the single Chinese-only `SPEC.md`, every human-facing document uses a regular English `*.md` file paired with a `*.cn.md` Chinese translation; the source tree contains no symlinks or duplicate language aliases. Regression tests cover rejected duplicate specifications, links from both languages to the shared specification, missing editions, legacy aliases, language drift, stale anchors, and rejected symlink metadata without creating symlinks.
- All requirement IDs match between the single SPEC and both coverage matrices; the original 24 MVP IDs remain stable.
- Tool names and order agree across SPEC and both editions of README, features, and the API reference.
- Markdown diffs contain no whitespace errors.

```bash
python3 scripts/check_docs.py
python3 -m pytest tests/unit/test_quality_constraints.py -q
git diff --check -- .
```
