"""Bounded, authenticated Streamable HTTP transport for trusted MCP clients."""

import asyncio
import contextlib
import hmac
import http.server
import ipaddress
import json
import re
import secrets
import socket
import socketserver
import ssl
import threading
import time
from typing import Any, Callable, Dict, Iterable, Optional, Tuple, Union, cast
from urllib.parse import urlsplit

from .main import ZellijMCPServer

SUPPORTED_PROTOCOL_VERSIONS = (
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
)
DEFAULT_HTTP_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[-1]
MIN_BEARER_TOKEN_CHARS = 32
MAX_BEARER_TOKEN_CHARS = 512
BEARER_TOKEN_RE = re.compile(r"^[A-Za-z0-9\-._~+/]+={0,2}$")
CRITICAL_SINGLE_HEADERS = (
    "Host",
    "Origin",
    "Authorization",
    "Content-Length",
    "MCP-Protocol-Version",
    "MCP-Session-Id",
)
HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*$"
)


def validate_bearer_token(token: str) -> bytes:
    """Return the ASCII token bytes or reject weak/unusable Bearer values."""
    if not isinstance(token, str):
        raise ValueError("Bearer token must be text")
    if not MIN_BEARER_TOKEN_CHARS <= len(token) <= MAX_BEARER_TOKEN_CHARS:
        raise ValueError(
            "Bearer token must contain between {} and {} characters".format(
                MIN_BEARER_TOKEN_CHARS,
                MAX_BEARER_TOKEN_CHARS,
            )
        )
    if BEARER_TOKEN_RE.fullmatch(token) is None:
        raise ValueError("Bearer token must use the ASCII Bearer token character set")
    return token.encode("ascii")


def validate_bind_host(host: str) -> str:
    """Return a canonical IP literal suitable for an explicit listener bind."""
    if not isinstance(host, str):
        raise ValueError("host must be an IPv4 or IPv6 address")
    try:
        return str(ipaddress.ip_address(host.strip()))
    except ValueError:
        raise ValueError("host must be an IPv4 or IPv6 address") from None


def is_loopback_bind_host(host: str) -> bool:
    """Return whether a validated listener address is loopback."""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _canonical_host(host: str) -> str:
    try:
        return str(ipaddress.ip_address(host.strip()))
    except ValueError:
        return host.strip().lower()


def _valid_authority_host(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return HOSTNAME_RE.fullmatch(host) is not None


def _split_host_port(
    value: str,
    default_port: Optional[int],
) -> Optional[Tuple[str, int]]:
    text = value.strip()
    if (
        not text
        or not text.isascii()
        or any(character.isspace() for character in text)
        or any(character in text for character in "\r\n/@?#\\%")
    ):
        return None
    port = default_port
    if text.startswith("["):
        closing = text.find("]")
        if closing <= 1:
            return None
        host = text[1:closing]
        suffix = text[closing + 1:]
        try:
            if not isinstance(ipaddress.ip_address(host), ipaddress.IPv6Address):
                return None
        except ValueError:
            return None
        if suffix:
            if not suffix.startswith(":") or not suffix[1:].isdigit():
                return None
            port = int(suffix[1:])
    else:
        if text.count(":") > 1:
            return None
        if ":" in text:
            host, raw_port = text.rsplit(":", 1)
            if not raw_port.isdigit():
                return None
            port = int(raw_port)
        else:
            host = text
    if not host or not _valid_authority_host(host):
        return None
    if port is None or not 1 <= port <= 65535:
        return None
    return _canonical_host(host), port


def _parse_allowed_host(value: str) -> Tuple[str, Optional[int]]:
    parsed = _split_host_port(value, 1)
    if parsed is None:
        raise ValueError("allowed host must be an ASCII hostname or IP with optional port")
    explicit_port = None
    text = value.strip()
    if text.startswith("["):
        if text[text.find("]") + 1:]:
            explicit_port = parsed[1]
    elif ":" in text:
        explicit_port = parsed[1]
    return parsed[0], explicit_port


def _parse_origin(value: str) -> Tuple[str, str, int]:
    if not isinstance(value, str) or not value or not value.isascii():
        raise ValueError("allowed origin must be an absolute ASCII http or https origin")
    if any(character.isspace() for character in value) or "\\" in value or "%" in value:
        raise ValueError("allowed origin must be an absolute ASCII http or https origin")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise ValueError("allowed origin must be an absolute ASCII http or https origin") from None
    if (
        parsed.scheme not in ("http", "https")
        or not host
        or not _valid_authority_host(host)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("allowed origin must be an absolute ASCII http or https origin")
    return parsed.scheme, _canonical_host(host), port or (443 if parsed.scheme == "https" else 80)


def create_server_ssl_context(cert_file: str, key_file: str) -> ssl.SSLContext:
    """Create a TLS 1.2+ server context without exposing certificate paths in errors."""
    if not cert_file or not key_file:
        raise ValueError("TLS certificate and key must be configured together")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.load_cert_chain(certfile=cert_file, keyfile=key_file)
    except (OSError, ssl.SSLError, ValueError):
        raise ValueError("unable to load TLS certificate and key") from None
    return context


def _accepts(header: str, media_type: str) -> bool:
    for item in header.split(","):
        parts = [part.strip().lower() for part in item.split(";")]
        if not parts or parts[0] != media_type:
            continue
        rejected = False
        for part in parts[1:]:
            if not part.startswith("q="):
                continue
            try:
                rejected = float(part[2:]) <= 0
            except ValueError:
                rejected = True
        if not rejected:
            return True
    return False


class _Session:
    def __init__(self, server: Any, protocol_version: str) -> None:
        self.server = server
        self.protocol_version = protocol_version
        self.initialized = False
        self.last_used = time.monotonic()
        self.lock = threading.Lock()


class _BoundedThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 32

    def __init__(self, server_address: Tuple[str, int], handler: Any, limit: int) -> None:
        self._request_slots = threading.BoundedSemaphore(limit)
        http.server.HTTPServer.__init__(self, server_address, handler)

    def process_request(
        self, request: Union[socket.socket, Tuple[bytes, socket.socket]], client_address: Any,
    ) -> None:
        # HTTPServer accepts TCP sockets; the shared socketserver stub also covers UDP.
        request = cast(socket.socket, request)
        if not self._request_slots.acquire(False):
            # Never initiate a TLS handshake on the accept loop when workers are full.
            if isinstance(request, ssl.SSLSocket):
                self.close_request(request)
                return
            with contextlib.suppress(OSError):
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Content-Length: 0\r\nConnection: close\r\n\r\n"
                )
            self.close_request(request)
            return
        try:
            socketserver.ThreadingMixIn.process_request(self, request, client_address)
        except Exception:
            self._request_slots.release()
            raise

    def process_request_thread(
        self, request: Union[socket.socket, Tuple[bytes, socket.socket]], client_address: Any,
    ) -> None:
        try:
            socketserver.ThreadingMixIn.process_request_thread(self, request, client_address)
        finally:
            self._request_slots.release()


class _BoundedThreadingHTTPServerV6(_BoundedThreadingHTTPServer):
    address_family = socket.AF_INET6


class StreamableHTTPTransport:
    """Expose one authenticated `/mcp` endpoint with isolated bounded sessions."""

    MAX_BODY_BYTES = 1024 * 1024
    MAX_RESPONSE_BYTES = 1024 * 1024
    MAX_SESSIONS = 64
    SESSION_TTL_SECONDS = 30 * 60
    READ_TIMEOUT_SECONDS = 5.0
    SESSION_LOCK_TIMEOUT_SECONDS = 5.0
    MAX_CONCURRENT_REQUESTS = 16

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        token: str = "",
        allowed_hosts: Optional[Iterable[str]] = None,
        allowed_origins: Optional[Iterable[str]] = None,
        tls_cert: Optional[str] = None,
        tls_key: Optional[str] = None,
        server_factory: Optional[Callable[[], Any]] = None,
        read_timeout: Optional[float] = None,
    ) -> None:
        self.host = validate_bind_host(host)
        if not isinstance(port, int) or isinstance(port, bool) or not 0 <= port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        self.token_bytes = validate_bearer_token(token)
        self.port = port
        configured_hosts = tuple(allowed_hosts or ())
        configured_origins = tuple(allowed_origins or ())
        self.allowed_hosts = tuple(_parse_allowed_host(value) for value in configured_hosts)
        self.allowed_origins = frozenset(_parse_origin(value) for value in configured_origins)
        self._auto_local_origin = (
            is_loopback_bind_host(self.host)
            and not configured_hosts
            and not configured_origins
        )
        if not is_loopback_bind_host(self.host) and not self.allowed_hosts:
            raise ValueError("non-loopback listeners require at least one allowed host")
        if not self.allowed_hosts:
            self.allowed_hosts = ((_canonical_host(self.host), None),)
        if bool(tls_cert) != bool(tls_key):
            raise ValueError("TLS certificate and key must be configured together")
        self.ssl_context = (
            create_server_ssl_context(tls_cert or "", tls_key or "")
            if tls_cert and tls_key
            else None
        )
        self.server_factory = server_factory or self._default_server_factory
        self.read_timeout = (
            self.READ_TIMEOUT_SECONDS if read_timeout is None else read_timeout
        )
        if self.read_timeout <= 0:
            raise ValueError("read timeout must be positive")
        self._sessions = {}  # type: Dict[str, _Session]
        self._sessions_lock = threading.Lock()
        self._httpd = None  # type: Optional[_BoundedThreadingHTTPServer]
        self.bound_port = port

    def _default_server_factory(self) -> ZellijMCPServer:
        return ZellijMCPServer(supported_protocol_versions=SUPPORTED_PROTOCOL_VERSIONS)

    def create_server(self) -> _BoundedThreadingHTTPServer:
        if self._httpd is not None:
            raise RuntimeError("HTTP server was already created")
        transport = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def setup(self) -> None:
                self.request.settimeout(transport.read_timeout)
                http.server.BaseHTTPRequestHandler.setup(self)

            def do_POST(self) -> None:
                transport._handle_post(self)

            def do_GET(self) -> None:
                transport._handle_method_not_allowed(self)

            def do_DELETE(self) -> None:
                transport._handle_delete(self)

            def do_HEAD(self) -> None:
                transport._handle_method_not_allowed(self)

            def do_OPTIONS(self) -> None:
                transport._handle_method_not_allowed(self)

            def do_PUT(self) -> None:
                transport._handle_method_not_allowed(self)

            def do_PATCH(self) -> None:
                transport._handle_method_not_allowed(self)

            def do_TRACE(self) -> None:
                transport._handle_method_not_allowed(self)

            def do_CONNECT(self) -> None:
                transport._handle_method_not_allowed(self)

            def send_error(
                self,
                code: int,
                message: Optional[str] = None,
                explain: Optional[str] = None,
            ) -> None:
                transport._empty_response(self, code)

            def log_message(self, unused_format: str, *unused_args: Any) -> None:
                return

        server_class = (
            _BoundedThreadingHTTPServerV6
            if isinstance(ipaddress.ip_address(self.host), ipaddress.IPv6Address)
            else _BoundedThreadingHTTPServer
        )
        try:
            self._httpd = server_class(
                (self.host, self.port),
                Handler,
                self.MAX_CONCURRENT_REQUESTS,
            )
            if self.ssl_context is not None:
                self._httpd.socket = self.ssl_context.wrap_socket(
                    self._httpd.socket,
                    server_side=True,
                    do_handshake_on_connect=False,
                )
        except (OSError, ssl.SSLError):
            if self._httpd is not None:
                self._httpd.server_close()
                self._httpd = None
            raise OSError("unable to bind or secure streamable-http listener") from None
        self.bound_port = int(self._httpd.server_address[1])
        return self._httpd

    def serve_forever(self) -> None:
        server = self.create_server()
        try:
            server.serve_forever()
        finally:
            server.server_close()
            self.close()

    def close(self) -> None:
        with self._sessions_lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.lock.acquire()
            try:
                session.server.close()
            except Exception:
                pass
            finally:
                session.lock.release()

    def _handle_post(self, handler: http.server.BaseHTTPRequestHandler) -> None:
        if not self._validate_common(handler):
            return
        if not self._valid_accept(handler.headers.get("Accept", "")):
            self._empty_response(handler, 406)
            return
        content_type = handler.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._empty_response(handler, 415)
            return
        if handler.headers.get_all("Transfer-Encoding") is not None:
            self._empty_response(handler, 400)
            return
        raw_length = handler.headers.get("Content-Length")
        try:
            content_length = int(raw_length) if raw_length is not None else -1
        except ValueError:
            content_length = -1
        if content_length < 0:
            self._empty_response(handler, 411)
            return
        if content_length > self.MAX_BODY_BYTES:
            self._empty_response(handler, 413)
            return
        try:
            body = handler.rfile.read(content_length)
        except socket.timeout:
            self._empty_response(handler, 408)
            return
        if len(body) != content_length:
            self._empty_response(handler, 400)
            return
        try:
            message = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            self._json_error(handler, 400, None, -32700, "Parse error")
            return
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            self._json_error(handler, 400, None, -32600, "Invalid JSON-RPC request")
            return

        method = message.get("method")
        is_response = method is None and "id" in message and (
            "result" in message or "error" in message
        )
        if is_response:
            acquired = self._acquire_session(handler)
            if acquired is None:
                return
            unused_session_id, session = acquired
            try:
                session.last_used = time.monotonic()
                self._empty_response(handler, 202)
            finally:
                session.lock.release()
            return
        if not isinstance(method, str):
            self._json_error(handler, 400, message.get("id"), -32600, "Invalid request")
            return
        is_notification = "id" not in message
        if method == "initialize" and not is_notification:
            self._handle_initialize(handler, message)
            return

        acquired = self._acquire_session(handler)
        if acquired is None:
            return
        unused_session_id, session = acquired
        try:
            if not session.initialized and method not in (
                "notifications/initialized",
                "ping",
            ):
                self._empty_response(handler, 400)
                return
            session.last_used = time.monotonic()
            response = self._run_message(session.server, message)
            if method == "notifications/initialized" and is_notification:
                session.initialized = True
            if is_notification or response is None:
                self._empty_response(handler, 202)
            else:
                self._json_response(handler, 200, response)
        finally:
            session.lock.release()

    def _handle_initialize(
        self,
        handler: http.server.BaseHTTPRequestHandler,
        message: Dict[str, Any],
    ) -> None:
        if handler.headers.get_all("MCP-Session-Id") is not None:
            self._empty_response(handler, 400)
            return
        validation_error = self._initialize_validation_error(message)
        if validation_error is not None:
            self._json_response(handler, 400, validation_error)
            return
        params = message["params"]
        requested = params["protocolVersion"]
        header_version = handler.headers.get("MCP-Protocol-Version")
        if header_version is not None and (
            header_version not in SUPPORTED_PROTOCOL_VERSIONS
            or header_version != requested
        ):
            self._empty_response(handler, 400)
            return
        negotiated = (
            requested
            if requested in SUPPORTED_PROTOCOL_VERSIONS
            else DEFAULT_HTTP_PROTOCOL_VERSION
        )
        self._expire_sessions()
        with self._sessions_lock:
            if len(self._sessions) >= self.MAX_SESSIONS:
                self._empty_response(handler, 503)
                return
            server = self.server_factory()
            session_id = secrets.token_urlsafe(32)
            session = _Session(server, negotiated)
            self._sessions[session_id] = session
        try:
            response = self._run_message(server, message)
        except Exception:
            with self._sessions_lock:
                if self._sessions.get(session_id) is session:
                    self._sessions.pop(session_id, None)
            with contextlib.suppress(Exception):
                server.close()
            self._json_error(handler, 500, message.get("id"), -32603, "Internal server error")
            return
        if response is None or "error" in response or not isinstance(response.get("result"), dict):
            with self._sessions_lock:
                if self._sessions.get(session_id) is session:
                    self._sessions.pop(session_id, None)
            server.close()
            if isinstance(response, dict) and "error" in response:
                self._json_response(handler, 400, response)
            else:
                self._json_error(handler, 500, message.get("id"), -32603, "Internal server error")
            return
        response["result"]["protocolVersion"] = negotiated
        self._json_response(
            handler,
            200,
            response,
            {"MCP-Session-Id": session_id},
        )

    def _initialize_validation_error(
        self,
        message: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        request_id = message.get("id")
        if "id" not in message or not (
            (
                isinstance(request_id, str)
                and len(request_id) <= ZellijMCPServer.MAX_RPC_ID_CHARS
            )
            or (isinstance(request_id, int) and type(request_id) is not bool)
        ):
            return self._rpc_error_value(None, -32600, "Invalid JSON-RPC request id")
        params = message.get("params")
        if not isinstance(params, dict):
            return self._rpc_error_value(request_id, -32602, "initialize params must be an object")
        protocol_version = params.get("protocolVersion")
        capabilities = params.get("capabilities")
        client_info = params.get("clientInfo")
        if not isinstance(protocol_version, str) or not protocol_version:
            return self._rpc_error_value(
                request_id,
                -32602,
                "initialize requires protocolVersion",
            )
        if not isinstance(capabilities, dict):
            return self._rpc_error_value(
                request_id,
                -32602,
                "initialize requires object capabilities",
            )
        if not isinstance(client_info, dict) or not all(
            isinstance(client_info.get(field), str) and client_info[field]
            for field in ("name", "version")
        ):
            return self._rpc_error_value(
                request_id,
                -32602,
                "initialize requires clientInfo name and version",
            )
        return None

    def _handle_delete(self, handler: http.server.BaseHTTPRequestHandler) -> None:
        if not self._validate_common(handler):
            return
        acquired = self._acquire_session(handler)
        if acquired is None:
            return
        session_id, session = acquired
        try:
            with self._sessions_lock:
                if self._sessions.get(session_id) is not session:
                    self._empty_response(handler, 404)
                    return
                self._sessions.pop(session_id, None)
            session.server.close()
            self._empty_response(handler, 204)
        finally:
            session.lock.release()

    def _validate_common(self, handler: http.server.BaseHTTPRequestHandler) -> bool:
        if not self._validate_single_headers(handler):
            self._empty_response(handler, 400)
            return False
        if handler.path != "/mcp":
            self._empty_response(handler, 404)
            return False
        authorization = handler.headers.get("Authorization", "")
        try:
            authorization_bytes = authorization.encode("ascii")
        except UnicodeEncodeError:
            authorization_bytes = b""
        prefix = b"Bearer "
        supplied = (
            authorization_bytes[len(prefix):]
            if authorization_bytes.startswith(prefix)
            else b""
        )
        if not hmac.compare_digest(supplied, self.token_bytes):
            self._empty_response(
                handler,
                401,
                {"WWW-Authenticate": 'Bearer realm="zellij-mcp"'},
            )
            return False
        host = _split_host_port(handler.headers.get("Host", ""), self.bound_port)
        if host is None or not any(
            host[0] == allowed_host
            and host[1] == (self.bound_port if allowed_port is None else allowed_port)
            for allowed_host, allowed_port in self.allowed_hosts
        ):
            self._empty_response(handler, 403)
            return False
        origin_values = handler.headers.get_all("Origin")
        if origin_values is not None:
            try:
                origin = _parse_origin(origin_values[0])
            except ValueError:
                self._empty_response(handler, 403)
                return False
            expected_scheme = "https" if self.ssl_context is not None else "http"
            if self._auto_local_origin:
                origin_allowed = origin == (expected_scheme, host[0], host[1])
            else:
                origin_allowed = origin in self.allowed_origins
            if not origin_allowed:
                self._empty_response(handler, 403)
                return False
        return True

    def _validate_single_headers(
        self,
        handler: http.server.BaseHTTPRequestHandler,
    ) -> bool:
        for name in CRITICAL_SINGLE_HEADERS:
            values = handler.headers.get_all(name)
            if values is not None and len(values) != 1:
                return False
        transfer_values = handler.headers.get_all("Transfer-Encoding")
        return transfer_values is None or len(transfer_values) == 1

    def _valid_accept(self, header: str) -> bool:
        return _accepts(header, "application/json") and _accepts(
            header,
            "text/event-stream",
        )

    def _acquire_session(
        self,
        handler: http.server.BaseHTTPRequestHandler,
    ) -> Optional[Tuple[str, _Session]]:
        session_id = handler.headers.get("MCP-Session-Id", "")
        if not session_id:
            self._empty_response(handler, 400)
            return None
        version = handler.headers.get("MCP-Protocol-Version")
        if version not in SUPPORTED_PROTOCOL_VERSIONS:
            self._empty_response(handler, 400)
            return None
        self._expire_sessions()
        with self._sessions_lock:
            session = self._sessions.get(session_id)
        if session is None:
            self._empty_response(handler, 404)
            return None
        if version != session.protocol_version:
            self._empty_response(handler, 400)
            return None
        if not session.lock.acquire(timeout=self.SESSION_LOCK_TIMEOUT_SECONDS):
            self._empty_response(handler, 503)
            return None
        with self._sessions_lock:
            current = self._sessions.get(session_id)
        if current is not session:
            session.lock.release()
            self._empty_response(handler, 404)
            return None
        return session_id, session

    def _expire_sessions(self) -> None:
        cutoff = time.monotonic() - self.SESSION_TTL_SECONDS
        with self._sessions_lock:
            candidates = [
                (session_id, session)
                for session_id, session in self._sessions.items()
                if session.last_used < cutoff
            ]
        for session_id, session in candidates:
            if not session.lock.acquire(False):
                continue
            try:
                with self._sessions_lock:
                    current = self._sessions.get(session_id)
                    if current is not session or session.last_used >= cutoff:
                        continue
                    self._sessions.pop(session_id, None)
                session.server.close()
            finally:
                session.lock.release()

    def _run_message(self, server: Any, message: Dict[str, Any]) -> Any:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(server.handle_rpc_message(message))
        finally:
            loop.close()

    def _handle_method_not_allowed(
        self,
        handler: http.server.BaseHTTPRequestHandler,
    ) -> None:
        if not self._validate_common(handler):
            return
        version = handler.headers.get("MCP-Protocol-Version")
        if version is not None and version not in SUPPORTED_PROTOCOL_VERSIONS:
            self._empty_response(handler, 400)
            return
        self._empty_response(handler, 405, {"Allow": "POST, DELETE"})

    def _rpc_error_value(
        self,
        request_id: Any,
        code: int,
        message: str,
    ) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    def _json_error(
        self,
        handler: http.server.BaseHTTPRequestHandler,
        status: int,
        request_id: Any,
        code: int,
        message: str,
    ) -> None:
        self._json_response(
            handler,
            status,
            self._rpc_error_value(request_id, code, message),
        )

    def _json_response(
        self,
        handler: http.server.BaseHTTPRequestHandler,
        status: int,
        value: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        body = self._serialize_json(value)
        if len(body) > self.MAX_RESPONSE_BYTES:
            fallback = self._rpc_error_value(
                value.get("id"),
                -32603,
                "Response too large",
            )
            body = self._serialize_json(fallback)
        response_headers = dict(headers or {})
        response_headers["Content-Type"] = "application/json"
        self._write_response(handler, status, body, response_headers)

    def _serialize_json(self, value: Dict[str, Any]) -> bytes:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            default=self._json_default,
        ).encode("utf-8")

    def _json_default(self, value: Any) -> Any:
        if hasattr(value, "dict"):
            return value.dict()
        if hasattr(value, "value"):
            return value.value
        return str(value)

    def _empty_response(
        self,
        handler: http.server.BaseHTTPRequestHandler,
        status: int,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self._write_response(handler, status, b"", headers or {})

    def _write_response(
        self,
        handler: http.server.BaseHTTPRequestHandler,
        status: int,
        body: bytes,
        headers: Dict[str, str],
    ) -> None:
        handler.close_connection = True
        try:
            handler.send_response(status)
            handler.send_header("Content-Length", str(len(body)))
            handler.send_header("Cache-Control", "no-store")
            handler.send_header("Connection", "close")
            for name, value in headers.items():
                handler.send_header(name, value)
            handler.end_headers()
            if body and handler.command != "HEAD":
                handler.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            return
