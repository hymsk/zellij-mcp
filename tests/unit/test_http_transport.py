"""Real loopback tests for the authenticated Streamable HTTP transport."""

import http.client
import json
import shutil
import socket
import ssl
import subprocess
import threading
import time
import traceback

import pytest

import zellij_mcp.cli as cli_module
from zellij_mcp.server.http_transport import StreamableHTTPTransport

TOKEN = "unit-test-bearer-token-0123456789abcdef"
ACCEPT = "application/json, text/event-stream"


class FakeHTTPServer:
    instances = []

    def __init__(self):
        self.calls = []
        self.closed = False
        self.cache = {}
        FakeHTTPServer.instances.append(self)

    async def handle_rpc_message(self, message):
        method = message.get("method")
        if "id" not in message:
            return None
        request_id = message.get("id")
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": message.get("params", {}).get("protocolVersion"),
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "fake", "version": "1"},
                },
            }
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": [{"name": "mock_tool"}]},
            }
        if method == "tools/call":
            arguments = message.get("params", {}).get("arguments", {})
            request_key = arguments.get("request_id")
            if request_key:
                self.cache[request_key] = self.cache.get(request_key, 0) + 1
            self.calls.append(arguments)
            payload = {
                "instance": FakeHTTPServer.instances.index(self),
                "cache_count": self.cache.get(request_key, 0),
                "arguments": arguments,
            }
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(payload)}],
                    "structuredContent": payload,
                    "isError": False,
                },
            }
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    def close(self):
        self.closed = True


def start_transport(**overrides):
    arguments = {
        "host": "127.0.0.1",
        "port": 0,
        "token": TOKEN,
        "server_factory": FakeHTTPServer,
    }
    arguments.update(overrides)
    transport = StreamableHTTPTransport(**arguments)
    server = transport.create_server()
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return transport, server, thread


def stop_transport(transport, server, thread):
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()
    transport.close()


@pytest.fixture
def http_server():
    FakeHTTPServer.instances = []
    transport, server, thread = start_transport()
    yield transport
    stop_transport(transport, server, thread)


def request(
    transport,
    method,
    path="/mcp",
    body=None,
    headers=None,
    connect_host=None,
    tls_context=None,
):
    target_host = connect_host or (
        "127.0.0.1"
        if transport.host == "0.0.0.0"
        else "::1"
        if transport.host == "::"
        else transport.host
    )
    connection_class = (
        http.client.HTTPSConnection
        if transport.ssl_context is not None
        else http.client.HTTPConnection
    )
    connection = connection_class(
        target_host,
        transport.bound_port,
        timeout=5,
        **({"context": tls_context} if transport.ssl_context is not None else {})
    )
    request_headers = dict(headers or {})
    encoded = None
    if body is not None:
        encoded = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
        request_headers.setdefault("Content-Length", str(len(encoded)))
    request_headers.setdefault("Host", "127.0.0.1:{}".format(transport.bound_port))
    connection.request(method, path, body=encoded, headers=request_headers)
    response = connection.getresponse()
    data = response.read()
    result = (response.status, dict(response.getheaders()), data)
    connection.close()
    return result


def auth_headers(transport, authority_host=None, **extra):
    host = authority_host or ("[::1]" if transport.host == "::1" else transport.host)
    headers = {
        "Authorization": "Bearer {}".format(TOKEN),
        "Accept": ACCEPT,
        "Host": "{}:{}".format(host, transport.bound_port),
    }
    headers.update(extra)
    return headers


def initialize(transport, version="2025-11-25", **header_overrides):
    headers = auth_headers(transport, **header_overrides)
    status, response_headers, body = request(
        transport,
        "POST",
        body={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": version,
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1"},
            },
        },
        headers=headers,
    )
    return status, response_headers, json.loads(body.decode("utf-8")) if body else None


def raw_request(transport, lines, body=b""):
    family = socket.AF_INET6 if transport.host == "::1" else socket.AF_INET
    connection = socket.socket(family, socket.SOCK_STREAM)
    connection.settimeout(5)
    connection.connect((transport.host, transport.bound_port))
    payload = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body
    connection.sendall(payload)
    chunks = []
    while True:
        try:
            chunk = connection.recv(65536)
        except ConnectionResetError:
            break
        if not chunk:
            break
        chunks.append(chunk)
    connection.close()
    return b"".join(chunks)


def session_headers(transport, session_id, version="2025-11-25", **extra):
    return auth_headers(
        transport,
        **dict({
            "MCP-Session-Id": session_id,
            "MCP-Protocol-Version": version,
        }, **extra)
    )


def test_initialize_initialized_list_and_call_over_real_loopback(http_server):
    status, headers, payload = initialize(http_server)
    session_id = headers["MCP-Session-Id"]

    assert status == 200
    assert headers["Content-Type"] == "application/json"
    assert payload["result"]["protocolVersion"] == "2025-11-25"

    status, unused_headers, body = request(
        http_server,
        "POST",
        body={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=session_headers(http_server, session_id),
    )
    assert status == 202
    assert body == b""

    status, unused_headers, body = request(
        http_server,
        "POST",
        body={"jsonrpc": "2.0", "id": 99, "result": {}},
        headers=session_headers(http_server, session_id),
    )
    assert status == 202
    assert body == b""

    status, unused_headers, body = request(
        http_server,
        "POST",
        body={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers=session_headers(http_server, session_id),
    )
    assert status == 200
    assert json.loads(body)["result"]["tools"] == [{"name": "mock_tool"}]

    status, unused_headers, body = request(
        http_server,
        "POST",
        body={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "mock_tool", "arguments": {"value": "safe"}},
        },
        headers=session_headers(http_server, session_id),
    )
    assert status == 200
    assert json.loads(body)["result"]["structuredContent"]["arguments"] == {"value": "safe"}


@pytest.mark.parametrize("version", ["2025-03-26", "2025-06-18", "2025-11-25"])
def test_supported_protocol_versions_are_negotiated_exactly(http_server, version):
    status, unused_headers, payload = initialize(http_server, version)
    assert status == 200
    assert payload["result"]["protocolVersion"] == version


def test_unsupported_initialize_version_negotiates_latest(http_server):
    status, unused_headers, payload = initialize(http_server, "2024-11-05")
    assert status == 200
    assert payload["result"]["protocolVersion"] == "2025-11-25"


@pytest.mark.parametrize(
    "message,code",
    [
        (
            {
                "jsonrpc": "2.0",
                "id": True,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
            -32600,
        ),
        (
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": []},
            -32602,
        ),
        (
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
            -32602,
        ),
        (
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test"},
                },
            },
            -32602,
        ),
    ],
)
def test_invalid_initialize_requests_return_rpc_400_without_session(http_server, message, code):
    status, headers, body = request(
        http_server,
        "POST",
        body=message,
        headers=auth_headers(http_server),
    )
    assert status == 400
    assert "MCP-Session-Id" not in headers
    assert json.loads(body)["error"]["code"] == code
    assert http_server._sessions == {}


def test_initialize_header_version_must_match_request(http_server):
    assert initialize(
        http_server,
        "2025-06-18",
        **{"MCP-Protocol-Version": "2025-11-25"}
    )[0] == 400


def test_initialize_rejects_even_empty_session_header(http_server):
    response = raw_request(http_server, [
        "POST /mcp HTTP/1.1",
        "Host: 127.0.0.1:{}".format(http_server.bound_port),
        "Authorization: Bearer {}".format(TOKEN),
        "Accept: {}".format(ACCEPT),
        "Content-Type: application/json",
        "MCP-Session-Id:",
        "Content-Length: 0",
    ])
    assert b" 400 " in response


def test_auth_origin_host_and_accept_are_enforced_without_reflecting_token(http_server):
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1"},
        },
    }
    status, headers, body = request(http_server, "POST", body=message, headers={"Accept": ACCEPT})
    assert status == 401
    assert headers["WWW-Authenticate"].startswith("Bearer")
    assert TOKEN.encode("utf-8") not in body

    status, unused_headers, body = request(
        http_server,
        "POST",
        body=message,
        headers=auth_headers(http_server, Origin="http://evil.example"),
    )
    assert status == 403
    assert TOKEN.encode("utf-8") not in body

    status, unused_headers, body = request(
        http_server,
        "POST",
        body=message,
        headers=auth_headers(http_server, Host="evil.example:{}".format(http_server.bound_port)),
    )
    assert status == 403
    assert body == b""

    status, unused_headers, unused_body = request(
        http_server,
        "POST",
        body=message,
        headers=auth_headers(http_server, Accept="application/json"),
    )
    assert status == 406

    origin = "http://127.0.0.1:{}".format(http_server.bound_port)
    assert initialize(http_server, Origin=origin)[0] == 200


def test_non_ascii_authorization_is_rejected_without_handler_failure(http_server):
    response = raw_request(http_server, [
        "POST /mcp HTTP/1.1",
        "Host: 127.0.0.1:{}".format(http_server.bound_port),
        "Authorization: Bearer café",
        "Accept: {}".format(ACCEPT),
        "Content-Type: application/json",
        "Content-Length: 0",
    ])
    assert b" 401 " in response
    assert b"Connection: close" in response


@pytest.mark.parametrize(
    "header_lines",
    [
        ["Host: 127.0.0.1:{port}", "Host: 127.0.0.1:{port}"],
        ["Authorization: Bearer {token}", "Authorization: Bearer {token}"],
        ["Origin:", "Origin: http://127.0.0.1:{port}"],
        ["Content-Length: 0", "Content-Length: 0"],
        ["MCP-Protocol-Version: 2025-11-25", "MCP-Protocol-Version: 2025-11-25"],
        ["MCP-Session-Id: one", "MCP-Session-Id: two"],
    ],
)
def test_duplicate_security_headers_are_rejected_and_connection_closed(
    http_server,
    header_lines,
):
    formatted = [
        line.format(port=http_server.bound_port, token=TOKEN)
        for line in header_lines
    ]
    names = {line.split(":", 1)[0].lower() for line in formatted}
    base = ["POST /mcp HTTP/1.1"]
    if "host" not in names:
        base.append("Host: 127.0.0.1:{}".format(http_server.bound_port))
    if "authorization" not in names:
        base.append("Authorization: Bearer {}".format(TOKEN))
    base.extend([
        "Accept: {}".format(ACCEPT),
        "Content-Type: application/json",
    ])
    if "content-length" not in names:
        base.append("Content-Length: 0")
    response = raw_request(http_server, base + formatted)
    assert b" 400 " in response
    assert b"Connection: close" in response


def test_host_query_fragment_empty_origin_and_empty_transfer_encoding_are_rejected(
    http_server,
):
    for special in (
        "Host: 127.0.0.1:{}?x=1".format(http_server.bound_port),
        "Host: 127.0.0.1:{}#fragment".format(http_server.bound_port),
        "Origin:",
        "Transfer-Encoding:",
    ):
        name = special.split(":", 1)[0].lower()
        lines = ["POST /mcp HTTP/1.1"]
        if name != "host":
            lines.append("Host: 127.0.0.1:{}".format(http_server.bound_port))
        lines.extend([
            "Authorization: Bearer {}".format(TOKEN),
            "Accept: {}".format(ACCEPT),
            "Content-Type: application/json",
            "Content-Length: 0",
            special,
        ])
        response = raw_request(http_server, lines)
        assert b" 400 " in response or b" 403 " in response
        assert b"Connection: close" in response


def test_early_error_closes_connection_without_parsing_pipelined_request(http_server):
    body = b"x" * 16
    first = [
        "POST /mcp HTTP/1.1",
        "Host: 127.0.0.1:{}".format(http_server.bound_port),
        "Authorization: Bearer wrong-token-value-that-is-long-enough",
        "Accept: {}".format(ACCEPT),
        "Content-Type: application/json",
        "Content-Length: {}".format(len(body)),
    ]
    pipelined = (
        b"GET /mcp HTTP/1.1\r\n"
        + "Host: 127.0.0.1:{}\r\n".format(http_server.bound_port).encode("ascii")
        + "Authorization: Bearer {}\r\n\r\n".format(TOKEN).encode("ascii")
    )
    response = raw_request(http_server, first, body + pipelined)
    assert response.count(b"HTTP/1.1") == 1
    assert b" 401 " in response
    assert b"Connection: close" in response


def test_method_content_type_transfer_encoding_path_and_body_limits(http_server):
    assert request(http_server, "GET", headers=auth_headers(http_server))[0] == 405
    assert request(http_server, "POST", path="/other", headers=auth_headers(http_server))[0] == 404

    status, unused_headers, unused_body = request(
        http_server,
        "POST",
        body=b"{}",
        headers=auth_headers(http_server, **{"Content-Type": "text/plain"}),
    )
    assert status == 415

    status, unused_headers, unused_body = request(
        http_server,
        "POST",
        body=b"{}",
        headers=auth_headers(http_server, **{"Transfer-Encoding": "gzip"}),
    )
    assert status == 400

    status, unused_headers, unused_body = request(
        http_server,
        "POST",
        body=b"x",
        headers=auth_headers(
            http_server,
            **{"Content-Length": str(http_server.MAX_BODY_BYTES + 1)}
        ),
    )
    assert status == 413

    status, unused_headers, body = request(
        http_server,
        "POST",
        body=b"not-json",
        headers=auth_headers(http_server),
    )
    assert status == 400
    assert json.loads(body)["error"]["code"] == -32700


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "PUT", "PATCH", "TRACE"])
def test_all_known_http_methods_apply_auth_origin_and_version_checks(http_server, method):
    assert request(http_server, method, headers={})[0] == 401
    assert request(
        http_server,
        method,
        headers=auth_headers(http_server, Origin="http://evil.example"),
    )[0] == 403
    assert request(
        http_server,
        method,
        headers=auth_headers(http_server, **{"MCP-Protocol-Version": "invalid"}),
    )[0] == 400
    status, headers, body = request(http_server, method, headers=auth_headers(http_server))
    assert status == 405
    assert headers["Connection"] == "close"
    if method == "HEAD":
        assert body == b""


@pytest.mark.skipif(not socket.has_ipv6, reason="IPv6 is unavailable")
def test_ipv6_loopback_uses_af_inet6_and_serves_requests():
    FakeHTTPServer.instances = []
    try:
        transport, server, thread = start_transport(host="::1")
    except OSError as exc:
        pytest.skip("IPv6 loopback cannot bind: {}".format(exc))
    try:
        assert server.address_family == socket.AF_INET6
        status, unused_headers, payload = initialize(transport)
        assert status == 200
        assert payload["result"]["protocolVersion"] == "2025-11-25"
    finally:
        stop_transport(transport, server, thread)


def test_version_header_session_delete_and_unknown_session_errors(http_server):
    status, headers, unused_payload = initialize(http_server, "2025-06-18")
    assert status == 200
    session_id = headers["MCP-Session-Id"]

    message = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    assert request(
        http_server,
        "POST",
        body=message,
        headers=auth_headers(http_server, **{"MCP-Session-Id": session_id}),
    )[0] == 400
    assert request(
        http_server,
        "POST",
        body=message,
        headers=session_headers(http_server, session_id, "2025-11-25"),
    )[0] == 400
    assert request(
        http_server,
        "POST",
        body=message,
        headers=session_headers(http_server, "missing", "2025-06-18"),
    )[0] == 404
    assert request(
        http_server,
        "DELETE",
        headers=auth_headers(http_server, **{"MCP-Session-Id": session_id}),
    )[0] == 400
    assert request(
        http_server,
        "DELETE",
        headers=session_headers(http_server, session_id, "2025-11-25"),
    )[0] == 400

    status, unused_headers, body = request(
        http_server,
        "DELETE",
        headers=session_headers(http_server, session_id, "2025-06-18"),
    )
    assert status == 204
    assert body == b""
    assert FakeHTTPServer.instances[0].closed is True
    assert request(
        http_server,
        "POST",
        body=message,
        headers=session_headers(http_server, session_id, "2025-06-18"),
    )[0] == 404


def test_sessions_isolate_request_id_state(http_server):
    unused_status, first_headers, unused_payload = initialize(http_server)
    unused_status, second_headers, unused_payload = initialize(http_server)
    first_id = first_headers["MCP-Session-Id"]
    second_id = second_headers["MCP-Session-Id"]

    for session_id in (first_id, second_id):
        request(
            http_server,
            "POST",
            body={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=session_headers(http_server, session_id),
        )
        status, unused_headers, body = request(
            http_server,
            "POST",
            body={
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "mock_tool",
                    "arguments": {"request_id": "same-client-id"},
                },
            },
            headers=session_headers(http_server, session_id),
        )
        assert status == 200
        assert json.loads(body)["result"]["structuredContent"]["cache_count"] == 1

    assert len(FakeHTTPServer.instances) == 2


def test_response_size_is_bounded_with_json_rpc_fallback(http_server):
    unused_status, headers, unused_payload = initialize(http_server)
    session_id = headers["MCP-Session-Id"]
    request(
        http_server,
        "POST",
        body={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=session_headers(http_server, session_id),
    )

    async def huge_response(message):
        return {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "result": {"text": "x" * (http_server.MAX_RESPONSE_BYTES + 1)},
        }

    FakeHTTPServer.instances[0].handle_rpc_message = huge_response
    status, unused_headers, body = request(
        http_server,
        "POST",
        body={"jsonrpc": "2.0", "id": 99, "method": "tools/list", "params": {}},
        headers=session_headers(http_server, session_id),
    )
    assert status == 200
    assert len(body) <= http_server.MAX_RESPONSE_BYTES
    assert json.loads(body)["error"]["message"] == "Response too large"


def test_session_capacity_and_ttl_expiry_are_enforced():
    FakeHTTPServer.instances = []
    transport, server, thread = start_transport()
    transport.MAX_SESSIONS = 1
    transport.SESSION_TTL_SECONDS = 0.01
    try:
        status, first_headers, unused_payload = initialize(transport)
        assert status == 200
        assert initialize(transport)[0] == 503
        first = FakeHTTPServer.instances[0]
        time.sleep(0.03)
        status, second_headers, unused_payload = initialize(transport)
        assert status == 200
        assert first.closed is True
        assert second_headers["MCP-Session-Id"] != first_headers["MCP-Session-Id"]
    finally:
        stop_transport(transport, server, thread)


def test_slow_body_times_out_and_closes_connection():
    FakeHTTPServer.instances = []
    transport, server, thread = start_transport(read_timeout=0.05)
    try:
        connection = socket.create_connection(("127.0.0.1", transport.bound_port), timeout=5)
        connection.settimeout(5)
        body = b"{}"
        headers = (
            "POST /mcp HTTP/1.1\r\n"
            "Host: 127.0.0.1:{port}\r\n"
            "Authorization: Bearer {token}\r\n"
            "Accept: {accept}\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: {length}\r\n\r\n"
        ).format(
            port=transport.bound_port,
            token=TOKEN,
            accept=ACCEPT,
            length=len(body),
        ).encode("ascii")
        connection.sendall(headers + body[:1])
        time.sleep(0.1)
        response = connection.recv(65536)
        connection.close()
        assert b" 408 " in response
        assert b"Connection: close" in response
    finally:
        stop_transport(transport, server, thread)


def test_concurrent_delete_waits_for_request_and_prevents_closed_runtime_execution():
    FakeHTTPServer.instances = []
    transport, server, thread = start_transport()
    entered = threading.Event()
    release = threading.Event()
    request_result = []
    delete_result = []
    try:
        unused_status, headers, unused_payload = initialize(transport)
        session_id = headers["MCP-Session-Id"]
        request(
            transport,
            "POST",
            body={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=session_headers(transport, session_id),
        )
        instance = FakeHTTPServer.instances[0]

        async def blocking(message):
            entered.set()
            release.wait(5)
            assert instance.closed is False
            return {"jsonrpc": "2.0", "id": message.get("id"), "result": {}}

        instance.handle_rpc_message = blocking

        request_thread = threading.Thread(target=lambda: request_result.append(request(
            transport,
            "POST",
            body={"jsonrpc": "2.0", "id": 8, "method": "tools/list", "params": {}},
            headers=session_headers(transport, session_id),
        )))
        delete_thread = threading.Thread(target=lambda: delete_result.append(request(
            transport,
            "DELETE",
            headers=session_headers(transport, session_id),
        )))
        request_thread.start()
        assert entered.wait(2)
        delete_thread.start()
        time.sleep(0.05)
        assert instance.closed is False
        assert delete_result == []
        release.set()
        request_thread.join(timeout=5)
        delete_thread.join(timeout=5)
        assert request_result[0][0] == 200
        assert delete_result[0][0] == 204
        assert instance.closed is True
        assert request(
            transport,
            "POST",
            body={"jsonrpc": "2.0", "id": 9, "method": "tools/list", "params": {}},
            headers=session_headers(transport, session_id),
        )[0] == 404
    finally:
        release.set()
        stop_transport(transport, server, thread)


def test_concurrency_limit_rejects_extra_connection():
    FakeHTTPServer.instances = []
    transport, server, thread = start_transport(read_timeout=1.0)
    transport.MAX_CONCURRENT_REQUESTS = 1
    try:
        stop_transport(transport, server, thread)
        transport = StreamableHTTPTransport(
            host="127.0.0.1",
            port=0,
            token=TOKEN,
            server_factory=FakeHTTPServer,
            read_timeout=1.0,
        )
        transport.MAX_CONCURRENT_REQUESTS = 1
        server = transport.create_server()
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()
        blocker = socket.create_connection(("127.0.0.1", transport.bound_port), timeout=5)
        blocker.sendall(b"POST /mcp HTTP/1.1\r\n")
        time.sleep(0.05)
        response = raw_request(transport, [
            "GET /mcp HTTP/1.1",
            "Host: 127.0.0.1:{}".format(transport.bound_port),
            "Authorization: Bearer {}".format(TOKEN),
        ])
        blocker.close()
        assert b" 503 " in response
        assert b"Connection: close" in response
    finally:
        stop_transport(transport, server, thread)


def test_http_transport_validates_listener_allowlists_and_token():
    with pytest.raises(ValueError, match="IPv4 or IPv6"):
        StreamableHTTPTransport(host="localhost", token=TOKEN)
    with pytest.raises(ValueError, match="allowed host"):
        StreamableHTTPTransport(host="0.0.0.0", token=TOKEN)
    with pytest.raises(ValueError, match="allowed host"):
        StreamableHTTPTransport(
            host="0.0.0.0",
            token=TOKEN,
            allowed_hosts=["bad host"],
        )
    with pytest.raises(ValueError, match="allowed origin"):
        StreamableHTTPTransport(
            host="127.0.0.1",
            token=TOKEN,
            allowed_origins=["https://example.test/path"],
        )
    with pytest.raises(ValueError, match="configured together"):
        StreamableHTTPTransport(
            host="127.0.0.1",
            token=TOKEN,
            tls_cert="certificate.pem",
        )
    with pytest.raises(ValueError, match="token"):
        StreamableHTTPTransport(host="127.0.0.1", token="")
    with pytest.raises(ValueError, match="ASCII"):
        StreamableHTTPTransport(host="127.0.0.1", token="界" * 32)
    with pytest.raises(ValueError, match="between"):
        StreamableHTTPTransport(host="127.0.0.1", token="short")


def test_cli_preserves_stdio_and_requires_environment_token(monkeypatch, capsys):
    events = []

    class FakeFacade:
        def serve_stdio(self):
            events.append(("stdio",))

        def serve_streamable_http(self, host, port, token, **options):
            events.append(("http", host, port, token, options))

        def close(self):
            events.append(("close",))

    monkeypatch.setattr(cli_module, "ZellijMCPServer", FakeFacade)
    monkeypatch.delenv(cli_module.HTTP_TOKEN_ENV, raising=False)

    assert cli_module._run_cli(["serve"]) == 0
    assert events == [("stdio",)]

    events[:] = []
    assert cli_module._run_cli(["serve", "--host", "0.0.0.0"]) == 2
    assert events == []
    assert "require --transport streamable-http" in capsys.readouterr().err

    events[:] = []
    assert cli_module._run_cli(["serve", "--transport", "streamable-http"]) == 2
    assert events == []
    assert cli_module.HTTP_TOKEN_ENV in capsys.readouterr().err

    events[:] = []
    token = "from-environment-token-0123456789abcdef"
    monkeypatch.setenv(cli_module.HTTP_TOKEN_ENV, token)
    assert cli_module._run_cli([
        "serve",
        "--transport",
        "streamable-http",
        "--host",
        "127.0.0.1",
        "--port",
        "9000",
    ]) == 0
    assert events == [(
        "http",
        "127.0.0.1",
        9000,
        token,
        {
            "allowed_hosts": [],
            "allowed_origins": [],
            "tls_cert": None,
            "tls_key": None,
        },
    )]


def test_wildcard_listener_is_reached_through_loopback_and_enforces_allowlists():
    FakeHTTPServer.instances = []
    transport, server, thread = start_transport(
        host="0.0.0.0",
        allowed_hosts=["mcp.internal:9443", "127.0.0.1"],
        allowed_origins=["http://client.internal:3000"],
    )
    try:
        status, unused_headers, payload = initialize(
            transport,
            Host="mcp.internal:9443",
        )
        assert status == 200
        assert payload["result"]["protocolVersion"] == "2025-11-25"
        assert initialize(transport, Host="127.0.0.1:9443")[0] == 403
        assert initialize(transport, Host="127.0.0.1:9999")[0] == 403
        assert initialize(
            transport,
            Host="mcp.internal:9443",
            Origin="http://client.internal:3000",
        )[0] == 200
        assert initialize(
            transport,
            Host="mcp.internal:9443",
            Origin="http://client.internal",
        )[0] == 403
        assert initialize(
            transport,
            Host="mcp.internal:9443",
            Origin="http://client.internal:3000/path",
        )[0] == 403
    finally:
        stop_transport(transport, server, thread)


def test_allowed_host_without_port_tracks_bound_port_for_tunnels():
    FakeHTTPServer.instances = []
    transport, server, thread = start_transport(
        host="0.0.0.0",
        allowed_hosts=["mcp.internal"],
    )
    try:
        assert initialize(
            transport,
            Host="mcp.internal:{}".format(transport.bound_port),
        )[0] == 200
        assert initialize(transport, Host="mcp.internal:443")[0] == 403
    finally:
        stop_transport(transport, server, thread)


@pytest.mark.skipif(not socket.has_ipv6, reason="IPv6 is unavailable")
def test_ipv6_wildcard_listener_is_reached_only_through_loopback_in_test():
    FakeHTTPServer.instances = []
    try:
        transport, server, thread = start_transport(
            host="::",
            allowed_hosts=["[::1]"],
        )
    except OSError as exc:
        pytest.skip("IPv6 wildcard cannot bind: {}".format(exc))
    try:
        assert server.address_family == socket.AF_INET6
        assert initialize(
            transport,
            Host="[::1]:{}".format(transport.bound_port),
        )[0] == 200
        assert initialize(
            transport,
            Host="[::]:{}".format(transport.bound_port),
        )[0] == 403
    finally:
        stop_transport(transport, server, thread)


def test_cli_warns_for_non_loopback_plain_http(monkeypatch, capsys):
    events = []

    class FakeFacade:
        def serve_streamable_http(self, host, port, token, **options):
            events.append((host, port, options))

        def close(self):
            return None

    monkeypatch.setattr(cli_module, "ZellijMCPServer", FakeFacade)
    monkeypatch.setenv(cli_module.HTTP_TOKEN_ENV, TOKEN)
    assert cli_module._run_cli([
        "serve",
        "--transport",
        "streamable-http",
        "--host",
        "0.0.0.0",
        "--allowed-host",
        "mcp.internal:8765",
    ]) == 0
    assert "trusted private network" in capsys.readouterr().err
    assert events[0][0] == "0.0.0.0"


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl is unavailable")
def test_native_https_handshake_bearer_auth_and_safe_tls_errors(tmp_path):
    cert_file = tmp_path / "server-cert.pem"
    key_file = tmp_path / "server-key.pem"
    subprocess.run([
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        "1",
        "-subj",
        "/CN=localhost",
        "-keyout",
        str(key_file),
        "-out",
        str(cert_file),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    FakeHTTPServer.instances = []
    transport, server, thread = start_transport(
        tls_cert=str(cert_file),
        tls_key=str(key_file),
    )
    assert transport.ssl_context.minimum_version == ssl.TLSVersion.TLSv1_2
    client_context = ssl.create_default_context(cafile=str(cert_file))
    client_context.check_hostname = True
    try:
        status, unused_headers, body = request(
            transport,
            "POST",
            body={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "tls-client", "version": "1"},
                },
            },
            headers=auth_headers(
                transport,
                authority_host="127.0.0.1",
                Origin="https://127.0.0.1:{}".format(transport.bound_port),
            ),
            connect_host="localhost",
            tls_context=client_context,
        )
        assert status == 200
        assert json.loads(body)["result"]["protocolVersion"] == "2025-11-25"
        status, unused_headers, body = request(
            transport,
            "POST",
            body={},
            headers={
                "Accept": ACCEPT,
                "Host": "127.0.0.1:{}".format(transport.bound_port),
            },
            connect_host="localhost",
            tls_context=client_context,
        )
        assert status == 401
        assert TOKEN.encode("ascii") not in body
    finally:
        stop_transport(transport, server, thread)

    secret_path = str(key_file)
    with pytest.raises(ValueError, match="unable to load TLS") as exc_info:
        StreamableHTTPTransport(
            host="127.0.0.1",
            token=TOKEN,
            tls_cert=str(cert_file),
            tls_key=secret_path + ".missing",
        )
    assert secret_path not in str(exc_info.value)
    formatted = "".join(traceback.format_exception(
        type(exc_info.value), exc_info.value, exc_info.value.__traceback__,
    ))
    assert secret_path not in formatted
    assert "FileNotFoundError" not in formatted
