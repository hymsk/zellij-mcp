"""Small shared types for the direct-pane MCP surface."""

from enum import Enum
from typing import Any, Dict, Optional


class ErrorCode(str, Enum):
    """Stable public MCP error codes."""

    INVALID_ARGUMENT = "invalid_argument"
    ZELLIJ_NOT_AVAILABLE = "zellij_not_available"
    WORKSPACE_NOT_FOUND = "workspace_not_found"
    PERMISSION_DENIED = "permission_denied"
    INTERNAL_ERROR = "internal_error"


class WorkspaceRef:
    """Address one live zellij pane by session and pane ID."""

    def __init__(self, resource_type: str, session: str, pane: str):
        self.type = resource_type
        self.session = session
        self.pane = pane

    def dict(self) -> Dict[str, str]:
        """Return the JSON-compatible public representation."""
        return {
            "type": self.type,
            "session": self.session,
            "pane": self.pane,
        }


class MCPError(Exception):
    """Stable error returned by MCP tools."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


class MutationOutcomeUnknownError(MCPError):
    """Report a mutation whose external result cannot be safely retried."""
