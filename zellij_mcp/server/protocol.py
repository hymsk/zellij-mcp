"""Bounded newline-delimited MCP JSON-RPC protocol handling."""

import asyncio
import json
import sys
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional, Tuple, cast

from .. import __version__

ToolCaller = Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]]


class MCPProtocol:
    """Handle MCP framing independently from zellij tool behavior."""

    SERVER_NAME = "zellij-mcp"
    SERVER_VERSION = __version__
    DEFAULT_PROTOCOL_VERSION = "2024-11-05"
    SERVER_INSTRUCTIONS = (
        "Use Zellij MCP when the user requests zellij, or a task needs a persistent "
        "interactive terminal, a background terminal task, or terminal access on a "
        "configured remote server. Otherwise, prefer the Host's normal execution tools. "
        "Discover existing resources before operating on them; preserve user focus "
        "and unrelated work."
    )
    MAX_RPC_MESSAGE_CHARS = 1024 * 1024
    MAX_RPC_RESPONSE_BYTES = 1024 * 1024
    MAX_RPC_ID_CHARS = 256
    MAX_ERROR_MESSAGE_CHARS = 4096

    def __init__(
        self,
        tools: Mapping[str, Dict[str, Any]],
        call_tool: ToolCaller,
        close_callback: Callable[[], None],
        supported_protocol_versions: Optional[Tuple[str, ...]] = None,
    ) -> None:
        self.tools = tools
        self.call_tool = call_tool
        self.close_callback = close_callback
        self.supported_protocol_versions = supported_protocol_versions

    async def handle_rpc_message(
        self,
        message: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Handle one JSON-RPC message from an MCP stdio client."""
        if not isinstance(message, dict):
            return self._rpc_error(None, -32600, "Invalid JSON-RPC request")
        request_id = message.get("id")
        if "id" in message and not (
            (
                isinstance(request_id, str)
                and len(request_id) <= self.MAX_RPC_ID_CHARS
            )
            or (isinstance(request_id, int) and type(request_id) is not bool)
        ):
            return self._rpc_error(None, -32600, "Invalid JSON-RPC request id")
        if message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return self._rpc_error(request_id, -32600, "Invalid JSON-RPC request")

        method = message["method"]
        is_notification = "id" not in message
        params_value = message.get("params") if "params" in message else None
        params = {} if params_value is None else params_value
        if not isinstance(params, dict):
            if is_notification:
                return None
            return self._rpc_error(request_id, -32602, "params must be an object")
        if is_notification or method.startswith("notifications/"):
            return None

        try:
            if method == "initialize":
                protocol_version = params.get("protocolVersion")
                if not isinstance(protocol_version, str) or not protocol_version:
                    protocol_version = self.DEFAULT_PROTOCOL_VERSION
                if (
                    self.supported_protocol_versions is not None
                    and protocol_version not in self.supported_protocol_versions
                ):
                    protocol_version = self.supported_protocol_versions[-1]
                return self._rpc_result(request_id, {
                    "protocolVersion": protocol_version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": self.SERVER_NAME,
                        "version": self.SERVER_VERSION,
                    },
                    "instructions": self.SERVER_INSTRUCTIONS,
                })
            if method in ("ping", "logging/setLevel"):
                return self._rpc_result(request_id, {})
            if method == "tools/list":
                return self._rpc_result(request_id, {"tools": list(self.tools.values())})
            if method == "tools/call":
                name = params.get("name")
                arguments_value = params.get("arguments") if "arguments" in params else None
                arguments = {} if arguments_value is None else arguments_value
                if not isinstance(name, str) or not isinstance(arguments, dict):
                    return self._rpc_error(
                        request_id,
                        -32602,
                        "tools/call requires string name and object arguments",
                    )
                tool_response = await self.call_tool(name, arguments)
                is_error = bool(tool_response.get("error"))
                payload = tool_response if is_error else tool_response.get("result", {})
                return self._bounded_tools_call_response(
                    request_id,
                    cast(Dict[str, Any], payload),
                    is_error,
                )
            return self._rpc_error(
                request_id,
                -32601,
                "Method not found: {}".format(method),
            )
        except Exception:
            return self._rpc_error(request_id, -32603, "Internal server error")

    def serve_stdio(self) -> None:
        """Serve newline-delimited MCP JSON-RPC over stdin/stdout."""
        try:
            previous_loop = asyncio.get_event_loop()
        except RuntimeError:
            previous_loop = None
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            while True:
                raw_line = sys.stdin.readline(self.MAX_RPC_MESSAGE_CHARS + 2)
                if raw_line == "":
                    break
                oversized = len(raw_line.rstrip("\r\n")) > self.MAX_RPC_MESSAGE_CHARS
                if len(raw_line) > self.MAX_RPC_MESSAGE_CHARS and not raw_line.endswith("\n"):
                    oversized = True
                    self._discard_stdio_line_tail()
                if oversized:
                    response = self._rpc_error(None, -32600, "Request too large")
                else:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        message = json.loads(line)
                    except (ValueError, RecursionError):
                        response = self._rpc_error(None, -32700, "Parse error")
                    else:
                        if not isinstance(message, dict):
                            response = self._rpc_error(None, -32600, "Invalid request")
                        else:
                            rpc_response = loop.run_until_complete(
                                self.handle_rpc_message(message)
                            )
                            if rpc_response is None:
                                continue
                            response = rpc_response
                try:
                    self._write_stdio_response(response)
                except BrokenPipeError:
                    return
        finally:
            self.close_callback()
            loop.close()
            asyncio.set_event_loop(previous_loop)

    def _discard_stdio_line_tail(self) -> None:
        while True:
            chunk = sys.stdin.readline(self.MAX_RPC_MESSAGE_CHARS + 2)
            if chunk == "" or chunk.endswith("\n"):
                return

    def _rpc_result(self, request_id: Any, result: Any) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _bounded_tools_call_response(
        self,
        request_id: Any,
        payload: Dict[str, Any],
        is_error: bool,
    ) -> Dict[str, Any]:
        """Keep duplicated MCP text/structured payloads within the stdio byte limit."""
        response = self._tools_call_response(request_id, payload, is_error)
        if len(self._json_dumps(response).encode("utf-8")) <= self.MAX_RPC_RESPONSE_BYTES:
            return response
        text = payload.get("text")
        if not isinstance(text, str):
            return response

        bounded_payload = dict(payload)
        bounded_payload["truncated"] = True
        low = 0
        high = len(text)
        best = ""
        while low <= high:
            middle = (low + high) // 2
            candidate = text[-middle:] if middle else ""
            bounded_payload["text"] = candidate
            candidate_response = self._tools_call_response(
                request_id,
                bounded_payload,
                is_error,
            )
            if (
                len(self._json_dumps(candidate_response).encode("utf-8"))
                <= self.MAX_RPC_RESPONSE_BYTES
            ):
                best = candidate
                low = middle + 1
            else:
                high = middle - 1
        bounded_payload["text"] = best
        return self._tools_call_response(request_id, bounded_payload, is_error)

    def _tools_call_response(
        self,
        request_id: Any,
        payload: Dict[str, Any],
        is_error: bool,
    ) -> Dict[str, Any]:
        return self._rpc_result(request_id, {
            "content": [{"type": "text", "text": self._json_dumps(payload)}],
            "structuredContent": payload,
            "isError": is_error,
        })

    def _rpc_error(self, request_id: Any, code: int, message: str) -> Dict[str, Any]:
        if len(message) > self.MAX_ERROR_MESSAGE_CHARS:
            message = message[: self.MAX_ERROR_MESSAGE_CHARS - 3] + "..."
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    def _write_stdio_response(self, response: Dict[str, Any]) -> None:
        serialized = self._json_dumps(response)
        if len(serialized.encode("utf-8")) > self.MAX_RPC_RESPONSE_BYTES:
            serialized = self._json_dumps(
                self._rpc_error(response.get("id"), -32603, "Response too large")
            )
        sys.stdout.write(serialized + "\n")
        sys.stdout.flush()

    def _json_dumps(self, value: Any) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            default=self._json_default,
        )

    def _json_default(self, value: Any) -> Any:
        if hasattr(value, "dict"):
            return value.dict()
        if hasattr(value, "value"):
            return value.value
        return str(value)
