"""Public MCP server facade composed from protocol and tool runtime layers."""

from typing import Any, Dict, Iterable, Optional, Tuple

from ..drivers.zellij import ZellijDriver
from .protocol import MCPProtocol
from .tool_runtime import ToolRuntime


class ZellijMCPServer:
    """Expose the bounded zellij tool runtime over stdio MCP."""

    SERVER_NAME = MCPProtocol.SERVER_NAME
    SERVER_VERSION = MCPProtocol.SERVER_VERSION
    DEFAULT_PROTOCOL_VERSION = MCPProtocol.DEFAULT_PROTOCOL_VERSION
    SERVER_INSTRUCTIONS = MCPProtocol.SERVER_INSTRUCTIONS
    MAX_RPC_MESSAGE_CHARS = MCPProtocol.MAX_RPC_MESSAGE_CHARS
    MAX_RPC_RESPONSE_BYTES = MCPProtocol.MAX_RPC_RESPONSE_BYTES
    MAX_RPC_ID_CHARS = MCPProtocol.MAX_RPC_ID_CHARS
    MAX_ERROR_MESSAGE_CHARS = MCPProtocol.MAX_ERROR_MESSAGE_CHARS
    MAX_PANE_SCREEN_CHARS = ToolRuntime.MAX_PANE_SCREEN_CHARS
    MAX_REQUEST_CACHE_ENTRIES = ToolRuntime.MAX_REQUEST_CACHE_ENTRIES

    def __init__(
        self,
        supported_protocol_versions: Optional[Tuple[str, ...]] = None,
    ) -> None:
        self.runtime = ToolRuntime()
        self.protocol = MCPProtocol(
            self.runtime.tools,
            self.runtime.call_tool,
            self.runtime.close,
            supported_protocol_versions=supported_protocol_versions,
        )

    @property
    def zellij(self) -> ZellijDriver:
        """Expose the driver for diagnostics and controlled test substitution."""
        return self.runtime.zellij

    @zellij.setter
    def zellij(self, value: ZellijDriver) -> None:
        self.runtime.zellij = value

    @property
    def tools(self) -> Dict[str, Dict[str, Any]]:
        return self.runtime.tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        self.runtime.MAX_REQUEST_CACHE_ENTRIES = self.MAX_REQUEST_CACHE_ENTRIES
        return await self.runtime.call_tool(name, arguments)

    async def handle_rpc_message(
        self,
        message: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return await self.protocol.handle_rpc_message(message)

    def serve_stdio(self) -> None:
        self.protocol.serve_stdio()

    def serve_streamable_http(
        self,
        host: str,
        port: int,
        token: str,
        allowed_hosts: Iterable[str] = (),
        allowed_origins: Iterable[str] = (),
        tls_cert: Optional[str] = None,
        tls_key: Optional[str] = None,
    ) -> None:
        """Serve isolated MCP sessions through the Streamable HTTP transport."""
        from .http_transport import StreamableHTTPTransport

        self.close()
        transport = StreamableHTTPTransport(
            host=host,
            port=port,
            token=token,
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
            tls_cert=tls_cert,
            tls_key=tls_key,
        )
        transport.serve_forever()

    def close(self) -> None:
        self.runtime.close()

    def _json_dumps(self, value: Any) -> str:
        return self.protocol._json_dumps(value)
