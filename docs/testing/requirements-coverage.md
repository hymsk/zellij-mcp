# SPEC Requirements Coverage Matrix

[中文](requirements-coverage.cn.md) | [English](requirements-coverage.md)

This matrix covers every requirement in the root [SPEC](../../SPEC.md): 24 direct pane requirements, 5 HTTP/HTTPS requirements, and 3 public interface requirements. Original `ZMCP-MVP-*` IDs are retained. Coverage locations do not mean that every environment has been tested or passed acceptance.

| ID | Requirement summary | Coverage evidence |
|----|---------------------|-------------------|
| ZMCP-MVP-001 | 11 public tools | Tool catalog order constraints, tools/list unit tests, and stdio scenarios |
| ZMCP-MVP-002 | MCP stdio protocol | Server protocol unit tests and stdio subprocess `server_smoke.py` |
| ZMCP-MVP-003 | Invoke only zellij | Static quality constraints and driver command checks |
| ZMCP-MVP-004 | Doctor dependency checks | Diagnostics, driver capability, and CLI tests |
| ZMCP-MVP-005 | Strict schemas | Server argument validation unit tests |
| ZMCP-MVP-006 | Structured argv | Tool schemas, driver commands, and KDL escaping tests |
| ZMCP-MVP-007 | Four workspace modes | Workspace handlers, `new-tab` focus restoration/pre-creation rejection tests, and creation integration scenarios |
| ZMCP-MVP-008 | Run command directly | `zellij_create_pane.py` and pane lifecycle scenarios |
| ZMCP-MVP-009 | Live session/pane discovery | Workspace list unit tests and real zellij scenarios |
| ZMCP-MVP-010 | Separate terminal/plugin panes | Pane normalization and count tests |
| ZMCP-MVP-011 | Stable tab_id | Tab handler, driver, and Tab lifecycle scenarios |
| ZMCP-MVP-012 | Direct routing to a specified Tab | Handler membership verification, `new-pane --tab-id` driver unit tests, and integration scenarios |
| ZMCP-MVP-013 | workspace_create new-tab parameters/results | Tab creation, focus, and command tests |
| ZMCP-MVP-014 | Exact resource targeting | session_name required schemas and cross-session mistargeting prevention tests |
| ZMCP-MVP-015 | Single-purpose input | Split tool required/unknown-field tests |
| ZMCP-MVP-016 | Fixed key enum | pane_send_key catalog and invalid-key tests |
| ZMCP-MVP-017 | Viewport/full | pane_screen parameter mapping tests |
| ZMCP-MVP-018 | ANSI option | ANSI preservation and removal tests |
| ZMCP-MVP-019 | 262144-character limit | Screen character, UTF-8 response byte, and bounded dump tests |
| ZMCP-MVP-020 | force=true | pane_close and tab_close rejection tests |
| ZMCP-MVP-021 | Protected pane targets | Pane safety unit tests and integration scenarios |
| ZMCP-MVP-022 | Protected Tab targets | Tab close safety tests |
| ZMCP-MVP-023 | Close verification and scope | Pane/Tab/session three-state outcomes, post-action discovery failure, and no proactive session deletion tests |
| ZMCP-MVP-024 | Common MCP Host acceptance | stdio server smoke and manual Host discovery/I/O acceptance steps |

## Transports and public interfaces

| ID | Requirement summary | Coverage evidence |
|----|---------------------|-------------------|
| ZMCP-HTTP-001 | HTTP protocol and version negotiation | [HTTP unit tests](../../tests/unit/test_http_transport.py): real loopback initialize/initialized/list/call, version negotiation, methods, and session headers |
| ZMCP-HTTP-002 | Authentication and access allowlists | [HTTP unit tests](../../tests/unit/test_http_transport.py): Bearer, Host/Origin, duplicate security headers, wildcard listener allowlists |
| ZMCP-HTTP-003 | Bounded sessions and resources | [HTTP unit tests](../../tests/unit/test_http_transport.py): request_id isolation, TTL/capacity, concurrent DELETE, connection limits, timeouts, and response limits; mocked tools without real zellij operations |
| ZMCP-HTTP-004 | Native HTTPS | [HTTP unit tests](../../tests/unit/test_http_transport.py): `test_native_https_handshake_bearer_auth_and_safe_tls_errors` verifies TLS, authentication, and configuration errors with temporary certificates |
| ZMCP-HTTP-005 | Explicit HTTP CLI activation | [HTTP unit tests](../../tests/unit/test_http_transport.py): default stdio, environment token, listener/allowlist/TLS validation, non-loopback plaintext warnings |
| ZMCP-API-001 | Machine-readable caller guidance | [Quality constraints](../../tests/unit/test_quality_constraints.py), [source smoke](../../tests/integration/server_smoke.py), and [installed smoke](../../tests/integration/installed_wheel_smoke.py): annotations, parameter descriptions, actual defaults, and initialize guidance |
| ZMCP-API-002 | Creation request deduplication | [Server unit tests](../../tests/unit/test_mcp_server.py): request_id replay/conflicts, cache capacity, failure release, and unknown-outcome protection; [driver unit tests](../../tests/unit/test_zellij_driver.py): unknown rollback outcomes |
| ZMCP-API-003 | Traceable installation provenance | Version literal, wheel/metadata, and English README long description checks in [quality constraints](../../tests/unit/test_quality_constraints.py); version provenance and package description checks in [installed smoke](../../tests/integration/installed_wheel_smoke.py) |

## Quality constraints

- All `ZMCP-*` ID sets must match exactly between the single Chinese-only SPEC and both language editions of this matrix.
- IDs must not be duplicated within a document.
- The original 24 MVP IDs remain stable; new requirements require corresponding coverage evidence.
- Tool catalog names and order must match SPEC and both editions of README and the API reference.

These consistency constraints are checked by `tests/unit/test_quality_constraints.py`. Real Hosts and cross-machine networks require separate acceptance in target environments; mocked tools and loopback tests do not replace it.
