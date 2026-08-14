"""Command-line interface for the Zellij MCP server."""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

from . import __version__
from .diagnostics import build_diagnostics
from .host_context import restore_zellij_context
from .provenance import source_provenance
from .server.main import ZellijMCPServer

HTTP_TOKEN_ENV = "ZELLIJ_MCP_HTTP_TOKEN"


def _json_dump(value: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _print_doctor(report: Dict[str, Any]) -> None:
    python_info = report["python"]
    zellij = report["zellij"]
    sys.stdout.write(
        "zellij-mcp {}\nPython {} ({})\n".format(
            report["zellij-mcp"]["version"],
            python_info["version"],
            "compatible" if python_info["compatible"] else "unsupported",
        )
    )
    if zellij.get("available"):
        sys.stdout.write("zellij: {}\n".format(zellij.get("version") or "available"))
        sys.stdout.write(
            "background sessions: {}\n".format(
                "supported" if zellij.get("supports_background_create") else "unsupported"
            )
        )
        sys.stdout.write(
            "stable Tab control: {}\n".format(
                "supported"
                if zellij.get("supports_stable_tab_control")
                else "unsupported"
            )
        )
        sys.stdout.write(
            "direct pane I/O: {}\n".format(
                "supported"
                if zellij.get("supports_direct_pane_io")
                else "unsupported"
            )
        )
    else:
        sys.stdout.write("zellij: unavailable (install separately)\n")
    for warning in report.get("warnings", []):
        sys.stdout.write("warning: {}\n".format(warning))
    for fix in report.get("fixes", []):
        sys.stdout.write("fix: {}\n".format(fix))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zellij-mcp")
    subparsers = parser.add_subparsers(dest="action")

    serve = subparsers.add_parser("serve", help="run the MCP server")
    serve.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
    )
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument(
        "--allowed-host",
        action="append",
        default=[],
        help=(
            "accepted HTTP Host authority; optional port is exact, omitted port uses "
            "the listener port; repeat for multiple values"
        ),
    )
    serve.add_argument(
        "--allowed-origin",
        action="append",
        default=[],
        help=(
            "accepted absolute http(s) Origin when Origin is present; repeat for "
            "multiple values"
        ),
    )
    serve.add_argument("--tls-cert", help="PEM certificate chain for native HTTPS")
    serve.add_argument("--tls-key", help="PEM private key for native HTTPS")

    doctor = subparsers.add_parser("doctor", help="check Python and zellij runtime state")
    doctor.add_argument("--json", action="store_true", dest="json_output")

    version = subparsers.add_parser("version", help="show the zellij-mcp version")
    version.add_argument("--json", action="store_true", dest="json_output")

    return parser


def _has_http_listener_options(namespace: argparse.Namespace) -> bool:
    return any((
        namespace.host != "127.0.0.1",
        namespace.port != 8765,
        namespace.allowed_host,
        namespace.allowed_origin,
        namespace.tls_cert,
        namespace.tls_key,
    ))


def _run_cli(arguments: List[str]) -> int:
    parser = _parser()
    namespace = parser.parse_args(arguments)

    if namespace.action == "serve":
        if namespace.transport == "stdio":
            if _has_http_listener_options(namespace):
                sys.stderr.write(
                    "streamable-http listener options require "
                    "--transport streamable-http\n"
                )
                return 2
            ZellijMCPServer().serve_stdio()
            return 0
        token = os.environ.get(HTTP_TOKEN_ENV, "")
        try:
            from .server.http_transport import (
                is_loopback_bind_host,
                validate_bearer_token,
                validate_bind_host,
            )

            validate_bearer_token(token)
            bind_host = validate_bind_host(namespace.host)
            if bool(namespace.tls_cert) != bool(namespace.tls_key):
                raise ValueError("TLS certificate and key must be configured together")
        except ValueError as exc:
            sys.stderr.write(
                "invalid streamable-http configuration (Bearer token from {}): {}\n".format(
                    HTTP_TOKEN_ENV,
                    exc,
                )
            )
            return 2
        if not is_loopback_bind_host(bind_host) and not namespace.tls_cert:
            sys.stderr.write(
                "warning: streamable-http is listening without TLS on a non-loopback "
                "address; use only on a trusted private network and prefer HTTPS.\n"
            )
        server = ZellijMCPServer()
        try:
            server.serve_streamable_http(
                bind_host,
                namespace.port,
                token,
                allowed_hosts=namespace.allowed_host,
                allowed_origins=namespace.allowed_origin,
                tls_cert=namespace.tls_cert,
                tls_key=namespace.tls_key,
            )
        except (OSError, ValueError) as exc:
            server.close()
            sys.stderr.write("unable to start streamable-http: {}\n".format(exc))
            return 2
        return 0

    if namespace.action == "version":
        result = {"name": "zellij-mcp", "version": __version__}
        result.update(source_provenance())
        if namespace.json_output:
            _json_dump(result)
        else:
            sys.stdout.write(__version__ + "\n")
        return 0

    if namespace.action == "doctor":
        report = build_diagnostics()
        if namespace.json_output:
            _json_dump(report)
        else:
            _print_doctor(report)
        return 0 if report["ok"] else 1

    parser.print_help()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Dispatch explicit runtime CLI commands."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "serve":
        restore_zellij_context()
    return _run_cli(arguments)


if __name__ == "__main__":
    sys.exit(main())
