"""Validated tool runtime for direct zellij pane management."""

import json
import math
import re
import shutil
import uuid
from typing import Any, Dict, List, Optional, cast

from ..core.types import ErrorCode, MCPError, MutationOutcomeUnknownError
from ..diagnostics import build_diagnostics
from ..drivers.zellij import ZellijDriver, ZellijMutationOutcomeUnknownError
from .tool_catalog import build_tool_catalog


class ToolRuntime:
    """Validate, dispatch and execute the exact public MCP tool contract."""

    MAX_PANE_SCREEN_CHARS = 262144
    MAX_REQUEST_CACHE_ENTRIES = 1024
    IDEMPOTENT_TOOLS = {"workspace_create"}
    ANSI_ESCAPE_RE = re.compile(
        r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"
    )

    def __init__(self) -> None:
        self.zellij = ZellijDriver()
        self.tools = build_tool_catalog()
        self._request_cache = {}  # type: Dict[str, Dict[str, Any]]
        self.handlers = {
            "zellij_mcp_doctor": self._handle_doctor,
            "workspace_create": self._handle_workspace_create,
            "workspace_list": self._handle_workspace_list,
            "tab_list": self._handle_tab_list,
            "tab_focus": self._handle_tab_focus,
            "tab_rename": self._handle_tab_rename,
            "tab_close": self._handle_tab_close,
            "pane_write_text": self._handle_pane_write_text,
            "pane_send_key": self._handle_pane_send_key,
            "pane_screen": self._handle_pane_screen,
            "pane_close": self._handle_pane_close,
        }
        if tuple(self.handlers) != tuple(self.tools):
            raise RuntimeError("MCP tool catalog and handlers are out of sync")

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call one public MCP tool and return a stable result wrapper."""
        try:
            if not isinstance(arguments, dict):
                raise MCPError(
                    code=ErrorCode.INVALID_ARGUMENT,
                    message="Tool arguments must be an object",
                )
            return {"result": await self._handle_tool(name, arguments)}
        except MCPError as error:
            return {
                "error": True,
                "code": error.code.value,
                "message": error.message,
                "details": error.details,
            }
        except Exception:
            return {
                "error": True,
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": "Internal server error",
            }

    def close(self) -> None:
        """Release runtime-local state; live zellij panes remain untouched."""
        self._request_cache.clear()

    def _validate_tool_arguments(self, name: str, arguments: Dict[str, Any]) -> None:
        tool = self.tools.get(name)
        if tool is None:
            raise MCPError(
                code=ErrorCode.INVALID_ARGUMENT,
                message="Unknown tool: {}".format(name),
            )
        schema = tool.get("inputSchema") or {}
        properties = schema.get("properties") or {}
        if schema.get("additionalProperties") is False:
            for field in arguments:
                if field not in properties:
                    self._raise_invalid_argument(field, "is not supported")
        for field in schema.get("required") or []:
            if field not in arguments:
                self._raise_invalid_argument(field, "is required")
            if isinstance(arguments.get(field), str) and not arguments[field]:
                self._raise_invalid_argument(field, "must not be empty")
        for field, value in arguments.items():
            field_schema = properties.get(field)
            if isinstance(field_schema, dict):
                self._validate_schema_value(field, value, field_schema)

    def _validate_schema_value(
        self,
        path: str,
        value: Any,
        schema: Dict[str, Any],
    ) -> None:
        expected_type = schema.get("type")
        valid = True
        if expected_type == "string":
            valid = isinstance(value, str)
        elif expected_type == "boolean":
            valid = type(value) is bool
        elif expected_type == "integer":
            valid = isinstance(value, int) and type(value) is not bool
        elif expected_type == "number":
            valid = isinstance(value, (int, float)) and type(value) is not bool
            if valid:
                valid = math.isfinite(float(value))
        elif expected_type == "array":
            valid = isinstance(value, list)
        elif expected_type == "object":
            valid = isinstance(value, dict)
        if not valid:
            self._raise_invalid_argument(path, "must be a {}".format(expected_type))
        if "enum" in schema and value not in schema["enum"]:
            self._raise_invalid_argument(path, "has an unsupported value")
        if isinstance(value, str):
            if "\x00" in value:
                self._raise_invalid_argument(path, "must not contain NUL")
            if len(value) < schema.get("minLength", 0):
                self._raise_invalid_argument(path, "is too short")
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                self._raise_invalid_argument(path, "is too long")
            max_bytes = schema.get("maxUtf8Bytes")
            if isinstance(max_bytes, int) and len(value.encode("utf-8")) > max_bytes:
                self._raise_invalid_argument(path, "is too large")
        if isinstance(value, list):
            if len(value) < schema.get("minItems", 0):
                self._raise_invalid_argument(path, "has too few items")
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                self._raise_invalid_argument(path, "has too many items")
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                for index, item in enumerate(value):
                    self._validate_schema_value(
                        "{}[{}]".format(path, index),
                        item,
                        item_schema,
                    )
            max_bytes = schema.get("maxUtf8Bytes")
            if isinstance(max_bytes, int):
                total = sum(
                    len(item.encode("utf-8"))
                    for item in value
                    if isinstance(item, str)
                )
                if total > max_bytes:
                    self._raise_invalid_argument(path, "is too large")
        if isinstance(value, dict):
            if "maxProperties" in schema and len(value) > schema["maxProperties"]:
                self._raise_invalid_argument(path, "has too many properties")
            pattern = schema.get("propertyNamePattern")
            if isinstance(pattern, str):
                for key in value:
                    if not isinstance(key, str) or re.fullmatch(pattern, key) is None:
                        self._raise_invalid_argument(path, "has an invalid property name")
            max_bytes = schema.get("maxUtf8Bytes")
            if isinstance(max_bytes, int):
                total = sum(
                    len(str(key).encode("utf-8")) + len(str(item).encode("utf-8"))
                    for key, item in value.items()
                )
                if total > max_bytes:
                    self._raise_invalid_argument(path, "is too large")
            item_schema = schema.get("additionalProperties")
            if isinstance(item_schema, dict):
                for key, item in value.items():
                    self._validate_schema_value(
                        "{}.{}".format(path, key),
                        item,
                        item_schema,
                    )
        if isinstance(value, (int, float)) and type(value) is not bool:
            if "minimum" in schema and value < schema["minimum"]:
                self._raise_invalid_argument(path, "is below the minimum")
            if "maximum" in schema and value > schema["maximum"]:
                self._raise_invalid_argument(path, "is above the maximum")

    def _raise_invalid_argument(self, path: str, reason: str) -> None:
        raise MCPError(
            code=ErrorCode.INVALID_ARGUMENT,
            message="Invalid argument '{}': {}".format(path, reason),
            details={"path": path, "reason": reason},
        )

    async def _handle_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        handler = self.handlers.get(name)
        if handler is None:
            raise MCPError(
                code=ErrorCode.INVALID_ARGUMENT,
                message="Unknown tool: {}".format(name),
            )
        self._validate_tool_arguments(name, arguments)
        cache_key = self._request_cache_key(name, arguments)
        if cache_key is not None:
            fingerprint = self._request_fingerprint(arguments)
            cached = self._request_cache.get(cache_key)
            if cached is not None:
                if cached["fingerprint"] != fingerprint:
                    raise MCPError(
                        code=ErrorCode.INVALID_ARGUMENT,
                        message="request_id was already used with different arguments",
                    )
                if "result" in cached:
                    return cast(Dict[str, Any], cached["result"])
                raise MCPError(
                    code=ErrorCode.INVALID_ARGUMENT,
                    message=(
                        "request_id has an unresolved prior attempt; inspect live resources "
                        "before using a new request_id"
                    ),
                )
            if len(self._request_cache) >= self.MAX_REQUEST_CACHE_ENTRIES:
                raise MCPError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=(
                        "request_id cache is full; restart the MCP server before "
                        "submitting a new create request"
                    ),
                )
            self._request_cache[cache_key] = {
                "fingerprint": fingerprint,
                "pending": True,
            }
        try:
            result = await handler(arguments)
        except MutationOutcomeUnknownError:
            raise
        except Exception:
            if cache_key is not None:
                self._request_cache.pop(cache_key, None)
            raise
        if cache_key is not None:
            self._request_cache[cache_key] = {
                "fingerprint": self._request_fingerprint(arguments),
                "result": json.loads(self._json_dumps(result)),
            }
        return result

    def _request_cache_key(
        self,
        name: str,
        arguments: Dict[str, Any],
    ) -> Optional[str]:
        if name not in self.IDEMPOTENT_TOOLS:
            return None
        request_id = arguments.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            return None
        return "{}\x00{}".format(name, request_id)

    def _request_fingerprint(self, arguments: Dict[str, Any]) -> str:
        return json.dumps(
            arguments,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

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

    async def _handle_doctor(self, args: Dict[str, Any]) -> Dict[str, Any]:
        report = build_diagnostics()
        zellij = report["zellij"]
        capabilities = dict(report["capabilities"])
        capabilities.update({
            "zellij": zellij.get("available", False),
            "zellij_background_create": zellij.get("supports_background_create", False),
            "zellij_stable_tab_control": zellij.get(
                "supports_stable_tab_control",
                False,
            ),
            "zellij_direct_pane_io": zellij.get("supports_direct_pane_io", True),
            "inside_zellij": zellij.get("inside_zellij", False),
            "host": "not_checked",
        })
        return {
            "ok": report["ok"],
            "zellij-mcp": report["zellij-mcp"],
            "python": report["python"],
            "zellij": zellij,
            "capabilities": capabilities,
            "warnings": report["warnings"],
            "fixes": report["fixes"],
        }

    def _list_sessions_checked(self) -> Optional[List[str]]:
        try:
            return self.zellij.list_sessions_checked()
        except Exception:
            return None

    def _list_panes_checked(
        self,
        session: str,
        include_plugins: bool = True,
    ) -> Optional[List[Dict[str, Any]]]:
        try:
            return self.zellij.list_panes_checked(
                session,
                include_plugins=include_plugins,
            )
        except Exception:
            return None

    def _list_tabs_checked(self, session: str) -> Optional[List[Dict[str, Any]]]:
        try:
            return self.zellij.list_tabs_checked(session)
        except Exception:
            return None

    def _resolve_session(self, session_name: Optional[str]) -> str:
        if not self.zellij.is_available():
            raise MCPError(
                code=ErrorCode.ZELLIJ_NOT_AVAILABLE,
                message="zellij is required; no other multiplexer is supported",
            )
        sessions = self._list_sessions_checked()
        if sessions is None:
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Unable to enumerate zellij sessions",
            )
        current = self.zellij.get_current_session()
        target = session_name or current
        if target is None and len(sessions) == 1:
            target = sessions[0]
        if not target:
            raise MCPError(
                code=ErrorCode.WORKSPACE_NOT_FOUND,
                message="No target zellij session; pass session_name",
                details={"available_sessions": sessions},
            )
        if target not in sessions and target != current:
            raise MCPError(
                code=ErrorCode.WORKSPACE_NOT_FOUND,
                message="Zellij session not found: {}".format(target),
                details={"available_sessions": sessions},
            )
        return target

    def _resolve_live_terminal_pane(
        self,
        session_name: Optional[str],
        pane_id: str,
    ) -> Dict[str, Any]:
        session = self._resolve_session(session_name)
        normalized = self.zellij.normalize_pane_id(pane_id)
        panes = self._list_panes_checked(session, include_plugins=True)
        if panes is None or not panes:
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Unable to enumerate panes in zellij session: {}".format(session),
                details={"session": session},
            )
        target = next(
            (item for item in panes if item.get("pane_id") == normalized),
            None,
        )
        if target is None:
            raise MCPError(
                code=ErrorCode.WORKSPACE_NOT_FOUND,
                message="Zellij pane not found: {}/{}".format(session, normalized),
            )
        if target.get("is_plugin"):
            raise MCPError(
                code=ErrorCode.PERMISSION_DENIED,
                message="Plugin panes cannot be controlled as terminal panes",
            )
        return {"session": session, "pane_id": normalized, "pane": target}

    def _current_mcp_identity_for_close(self) -> Optional[Dict[str, str]]:
        """Resolve the current MCP pane or refuse destructive work when ambiguous."""
        if not self.zellij.is_inside_zellij():
            return None
        session = self.zellij.get_current_session()
        pane_id = self.zellij.get_current_pane_id()
        if not session or not pane_id:
            raise MCPError(
                code=ErrorCode.PERMISSION_DENIED,
                message=(
                    "Refusing to close zellij resources without a complete "
                    "current MCP identity"
                ),
            )
        sessions = self._list_sessions_checked()
        panes = self._list_panes_checked(session, include_plugins=True)
        if (
            sessions is None
            or session not in sessions
            or panes is None
            or not any(item.get("pane_id") == pane_id for item in panes)
        ):
            raise MCPError(
                code=ErrorCode.PERMISSION_DENIED,
                message=(
                    "Refusing to close zellij resources because the current MCP "
                    "identity is stale"
                ),
            )
        return {"session": session, "pane_id": pane_id}

    def _single_active_tab(
        self,
        tabs: Optional[List[Dict[str, Any]]],
    ) -> Optional[Dict[str, Any]]:
        if tabs is None:
            return None
        active = [item for item in tabs if item.get("active") is True]
        return active[0] if len(active) == 1 else None

    def _tab_focus_verified(
        self,
        tabs: Optional[List[Dict[str, Any]]],
        tab_id: int,
    ) -> Optional[bool]:
        active = self._single_active_tab(tabs)
        return None if active is None else active.get("tab_id") == tab_id

    def _workspace_command(self, command: Any, environment: Any) -> Any:
        if not environment:
            return command
        env_path = shutil.which("env")
        if not env_path:
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Cannot apply workspace environment because env is unavailable",
            )
        assignments = [
            "{}={}".format(key, environment[key])
            for key in sorted(environment)
        ]
        return [env_path] + assignments + list(command)

    async def _handle_workspace_create(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.zellij.is_available():
            raise MCPError(
                code=ErrorCode.ZELLIJ_NOT_AVAILABLE,
                message="zellij is required; no other multiplexer is supported",
            )
        command = self._workspace_command(args["command"], args.get("environment"))
        cwd = args.get("cwd")
        mode = args.get("workspace_type", "auto")
        session_name = args.get("session_name")
        tab_id = args.get("tab_id")
        tab_name = args.get("tab_name")
        return_tab_id = args.get("return_tab_id")
        focus = bool(args.get("focus", False))
        if focus and return_tab_id is not None:
            raise MCPError(
                code=ErrorCode.INVALID_ARGUMENT,
                message="workspace_create return_tab_id requires focus=false",
            )
        if mode == "auto":
            mode = (
                "new-tab"
                if self.zellij.is_inside_zellij() or session_name
                else "new-session"
            )
        if mode not in ("new-pane", "new-tab") and (
            tab_id is not None or tab_name is not None or return_tab_id is not None or focus
        ):
            raise MCPError(
                code=ErrorCode.INVALID_ARGUMENT,
                message=(
                    "workspace_create tab_id, tab_name, return_tab_id and focus are only "
                    "supported for new-pane or new-tab"
                ),
            )
        if mode == "new-pane" and return_tab_id is not None and tab_id is None:
            raise MCPError(
                code=ErrorCode.INVALID_ARGUMENT,
                message="workspace_create new-pane return_tab_id requires tab_id",
            )
        if mode == "new-pane" and tab_id is not None and not session_name:
            raise MCPError(
                code=ErrorCode.INVALID_ARGUMENT,
                message="workspace_create new-pane tab_id requires session_name",
            )
        if mode == "new-pane" and tab_name is not None:
            raise MCPError(
                code=ErrorCode.INVALID_ARGUMENT,
                message="workspace_create new-pane does not accept tab_name",
            )

        previous_tab = None  # type: Optional[Dict[str, Any]]
        target_session = None  # type: Optional[str]
        if mode == "new-pane":
            target_session = self._resolve_session(session_name)
            panes_before = self._list_panes_checked(
                target_session,
                include_plugins=True,
            )
            if panes_before is None:
                raise MCPError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message="Unable to enumerate zellij panes before creation",
                )
            if tab_id is not None:
                tabs = self._list_tabs_checked(target_session)
                if tabs is None:
                    raise MCPError(
                        code=ErrorCode.INTERNAL_ERROR,
                        message="Unable to enumerate zellij tabs: {}".format(target_session),
                    )
                if not any(item.get("tab_id") == tab_id for item in tabs):
                    raise MCPError(
                        code=ErrorCode.WORKSPACE_NOT_FOUND,
                        message="Zellij Tab not found: {}/{}".format(target_session, tab_id),
                    )
                if return_tab_id is not None and not any(
                    item.get("tab_id") == return_tab_id for item in tabs
                ):
                    raise MCPError(
                        code=ErrorCode.WORKSPACE_NOT_FOUND,
                        message="Zellij return Tab not found: {}/{}".format(
                            target_session,
                            return_tab_id,
                        ),
                    )
                previous_tab = self._single_active_tab(tabs)
            try:
                workspace = self.zellij.create_pane(
                    session=target_session,
                    cwd=cwd,
                    command=command,
                    tab_id=tab_id,
                )
            except ZellijMutationOutcomeUnknownError as exc:
                raise MutationOutcomeUnknownError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=str(exc),
                ) from exc
        elif mode == "new-session":
            target_session = session_name or "zellij-mcp-{}".format(uuid.uuid4().hex[:12])
            presence = self.zellij.session_presence(target_session)
            if presence is None:
                raise MCPError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message="Unable to confirm whether zellij session exists: {}".format(
                        target_session
                    ),
                )
            if presence:
                raise MCPError(
                    code=ErrorCode.INVALID_ARGUMENT,
                    message="workspace_type=new-session requires a new session name",
                    details={"session_name": target_session},
                )
            try:
                workspace = self.zellij.create_session_with_command(
                    target_session,
                    cwd=cwd,
                    command=command,
                )
            except ZellijMutationOutcomeUnknownError as exc:
                raise MutationOutcomeUnknownError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=str(exc),
                ) from exc
        elif mode == "new-tab":
            target_session = self._resolve_session(session_name)
            tabs_before = self._list_tabs_checked(target_session)
            if tabs_before is None:
                raise MCPError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message="Unable to enumerate zellij tabs: {}".format(target_session),
                )
            if return_tab_id is not None and not any(
                item.get("tab_id") == return_tab_id for item in tabs_before
            ):
                raise MCPError(
                    code=ErrorCode.WORKSPACE_NOT_FOUND,
                    message="Zellij return Tab not found: {}/{}".format(
                        target_session,
                        return_tab_id,
                    ),
                )
            try:
                tab_id = self.zellij.create_tab(
                    session=target_session,
                    name=tab_name,
                    cwd=cwd,
                    command=command,
                )
            except ZellijMutationOutcomeUnknownError as exc:
                raise MutationOutcomeUnknownError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=str(exc),
                ) from exc
            if tab_id is None:
                raise MCPError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message="Unable to create zellij Tab in session: {}".format(target_session),
                )
            # For new-tab mode, we return tab info instead of pane info
            tabs_now = self._list_tabs_checked(target_session)
            created = next(
                (item for item in (tabs_now or []) if item.get("tab_id") == tab_id),
                None,
            )
            if tabs_now is None or created is None:
                raise MutationOutcomeUnknownError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message="Created zellij Tab could not be confirmed",
                )
            # Handle focus logic for new-tab mode
            tab_focus_action_accepted = None
            expected_final_created_tab = tab_id if focus else None
            focus_conflict = False
            if focus:
                tab_focus_action_accepted = self.zellij.focus_tab(
                    target_session,
                    tab_id,
                )
            elif return_tab_id is not None:
                expected_final_created_tab = return_tab_id
                tab_focus_action_accepted = self.zellij.focus_tab(
                    target_session,
                    return_tab_id,
                )
            tabs_after = self._list_tabs_checked(target_session)
            focus_verified = (
                self._tab_focus_verified(tabs_after, expected_final_created_tab)
                if expected_final_created_tab is not None
                else None
            )
            return {
                "workspace_ref": {"type": "tab", "session": target_session, "tab": tab_id},
                "session": target_session,
                "tab_id": tab_id,
                "tab": created,
                "attach_hint": "zellij attach {}".format(target_session),
                "direct": True,
                "focus_requested": focus,
                "focus_verified": focus_verified,
                "focus_action_accepted": tab_focus_action_accepted,
                "focus_conflict": focus_conflict,
                "degraded": (
                    expected_final_created_tab is not None
                    and focus_verified is not True
                ),
            }
        else:
            raise MCPError(
                code=ErrorCode.INVALID_ARGUMENT,
                message="Unsupported workspace_type: {}".format(mode),
            )
        if workspace is None:
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Unable to create zellij workspace",
            )

        session = workspace.session
        pane_id = workspace.pane
        panes = self._list_panes_checked(session, include_plugins=True)
        pane_info = next(
            (item for item in (panes or []) if item.get("pane_id") == pane_id),
            None,
        )
        if panes is None or pane_info is None:
            raise MutationOutcomeUnknownError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Created zellij pane could not be confirmed",
            )
        if tab_id is not None and pane_info.get("tab_id") != tab_id:
            raise MutationOutcomeUnknownError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Created zellij pane is not in the requested Tab",
                details={
                    "requested_tab_id": tab_id,
                    "actual_tab_id": pane_info.get("tab_id"),
                    "pane_id": pane_id,
                },
            )
        created_tab_id = tab_id
        if created_tab_id is None:
            created_tab_id = pane_info.get("tab_id")

        focus_action_accepted = None  # type: Optional[bool]
        expected_final_tab = None  # type: Optional[int]
        focus_conflict = False
        if tab_id is not None:
            if focus:
                expected_final_tab = tab_id
                focus_action_accepted = self.zellij.focus_tab(session, tab_id)
            elif return_tab_id is not None:
                expected_final_tab = return_tab_id
                focus_action_accepted = self.zellij.focus_tab(session, return_tab_id)
            elif previous_tab is not None:
                previous_tab_id = previous_tab.get("tab_id")
                if isinstance(previous_tab_id, int):
                    tabs_now = self._list_tabs_checked(session)
                    active_now = self._single_active_tab(tabs_now)
                    active_now_id = active_now.get("tab_id") if active_now else None
                    if active_now_id == tab_id:
                        expected_final_tab = previous_tab_id
                        focus_action_accepted = self.zellij.focus_tab(
                            session,
                            previous_tab_id,
                        )
                    elif active_now_id == previous_tab_id:
                        expected_final_tab = previous_tab_id
                    elif active_now_id is not None:
                        expected_final_tab = cast(int, active_now_id)
                        focus_conflict = True
                    else:
                        expected_final_tab = previous_tab_id
        tabs_after = self._list_tabs_checked(session) if tab_id is not None else None
        focus_verified = (
            self._tab_focus_verified(tabs_after, expected_final_tab)
            if expected_final_tab is not None
            else None
        )
        return {
            "workspace_ref": workspace.dict(),
            "session": session,
            "pane_id": pane_id,
            "tab_id": created_tab_id,
            "attach_hint": "zellij attach {}".format(session),
            "direct": True,
            "focus_requested": focus if tab_id is not None else None,
            "focus_restored": focus_verified if tab_id is not None and not focus else None,
            "focus_verified": focus_verified,
            "focus_action_accepted": focus_action_accepted,
            "focus_conflict": focus_conflict,
            "degraded": expected_final_tab is not None and focus_verified is not True,
        }

    async def _handle_workspace_list(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.zellij.is_available():
            raise MCPError(
                code=ErrorCode.ZELLIJ_NOT_AVAILABLE,
                message="zellij is required; no other multiplexer is supported",
            )
        session_name = args.get("session_name")
        all_sessions = bool(args.get("all_sessions", False))
        include_plugins = bool(args.get("include_plugins", False))
        current_session = self.zellij.get_current_session()
        sessions = self._list_sessions_checked()
        if sessions is None:
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Unable to enumerate zellij sessions",
            )
        if session_name:
            targets = [session_name]
        elif all_sessions:
            targets = sessions
        elif current_session:
            targets = [current_session]
        elif len(sessions) == 1:
            targets = sessions
        else:
            targets = []
        if not targets:
            raise MCPError(
                code=ErrorCode.WORKSPACE_NOT_FOUND,
                message="No target zellij session; pass session_name or all_sessions=true",
                details={"available_sessions": sessions},
            )
        if session_name and session_name not in sessions and session_name != current_session:
            raise MCPError(
                code=ErrorCode.WORKSPACE_NOT_FOUND,
                message="Zellij session not found: {}".format(session_name),
                details={"available_sessions": sessions},
            )
        payloads = []  # type: List[Dict[str, Any]]
        failed = []  # type: List[str]
        for target in targets:
            summary = self.zellij.get_session_summary(
                target,
                include_plugins=include_plugins,
            )
            if summary is None:
                failed.append(target)
            else:
                payloads.append(summary)
        if not payloads:
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Unable to read panes from the selected zellij session",
                details={"failed_sessions": failed},
            )
        terminal_count = sum(item["terminal_pane_count"] for item in payloads)
        plugin_count = sum(item["plugin_pane_count"] for item in payloads)
        return {
            "current_session": current_session,
            "current_pane": self.zellij.get_current_pane_id(),
            "session_count": len(payloads),
            "total_pane_count": terminal_count + plugin_count,
            "pane_count": terminal_count,
            "terminal_pane_count": terminal_count,
            "plugin_pane_count": plugin_count,
            "sessions": payloads,
            "degraded": bool(failed),
            "failed_sessions": failed,
        }

    def _tab_session_payload(
        self,
        session: str,
        include_panes: bool,
    ) -> Dict[str, Any]:
        tabs = self._list_tabs_checked(session)
        panes = self._list_panes_checked(session, include_plugins=True)
        if tabs is None or panes is None or not panes:
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Unable to enumerate zellij tabs or panes: {}".format(session),
            )
        tab_ids = {
            item.get("tab_id")
            for item in tabs
            if isinstance(item.get("tab_id"), int)
        }
        unmapped = [
            item
            for item in panes
            if item.get("tab_id") not in tab_ids
            and not (len(tabs) == 1 and item.get("tab_id") is None)
        ]
        if unmapped:
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Unable to confirm pane membership for zellij tabs",
                details={"unmapped_pane_ids": [item.get("pane_id") for item in unmapped]},
            )
        result_tabs = []  # type: List[Dict[str, Any]]
        for tab in tabs:
            tab_id = tab.get("tab_id")
            matching = [
                item
                for item in panes
                if item.get("tab_id") == tab_id
                or (len(tabs) == 1 and item.get("tab_id") is None)
            ]
            terminal = [item for item in matching if not item.get("is_plugin")]
            plugin = [item for item in matching if item.get("is_plugin")]
            payload = dict(tab)
            payload.update({
                "total_pane_count": len(matching),
                "pane_count": len(terminal),
                "terminal_pane_count": len(terminal),
                "plugin_pane_count": len(plugin),
            })
            if include_panes:
                payload["panes"] = matching
            result_tabs.append(payload)
        active = self._single_active_tab(result_tabs)
        return {
            "session": session,
            "is_current": session == self.zellij.get_current_session(),
            "active_tab_id": active.get("tab_id") if active else None,
            "active_tab_source": active.get("active_source") if active else None,
            "tab_count": len(result_tabs),
            "tabs": result_tabs,
        }

    async def _handle_tab_list(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if args.get("session_name") and args.get("all_sessions"):
            raise MCPError(
                code=ErrorCode.INVALID_ARGUMENT,
                message="Choose session_name or all_sessions=true, not both",
            )
        if args.get("all_sessions"):
            targets = self._list_sessions_checked()
            if targets is None:
                raise MCPError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message="Unable to enumerate zellij sessions",
                )
        else:
            targets = [self._resolve_session(args.get("session_name"))]
        sessions = [
            self._tab_session_payload(target, bool(args.get("include_panes", True)))
            for target in targets
        ]
        return {
            "current_session": self.zellij.get_current_session(),
            "current_pane": self.zellij.get_current_pane_id(),
            "session_count": len(sessions),
            "tab_count": sum(item["tab_count"] for item in sessions),
            "sessions": sessions,
            "degraded": False,
            "failed_sessions": [],
        }

    async def _handle_tab_focus(self, args: Dict[str, Any]) -> Dict[str, Any]:
        session = self._resolve_session(args.get("session_name"))
        tab_id = cast(int, args["tab_id"])
        tabs = self._list_tabs_checked(session)
        if tabs is None or not any(item.get("tab_id") == tab_id for item in tabs):
            raise MCPError(
                code=(
                    ErrorCode.INTERNAL_ERROR
                    if tabs is None
                    else ErrorCode.WORKSPACE_NOT_FOUND
                ),
                message="Zellij Tab not found or unavailable: {}/{}".format(session, tab_id),
            )
        previous = self._single_active_tab(tabs)
        changed = previous is None or previous.get("tab_id") != tab_id
        if changed and not self.zellij.focus_tab(session, tab_id):
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Failed to focus zellij Tab: {}/{}".format(session, tab_id),
            )
        tabs_after = self._list_tabs_checked(session)
        verified = self._tab_focus_verified(tabs_after, tab_id)
        if verified is False:
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Zellij Tab focus postcondition failed",
            )
        return {
            "focused": True,
            "changed": changed,
            "session": session,
            "tab_id": tab_id,
            "previous_tab_id": previous.get("tab_id") if previous else None,
            "focus_verified": verified,
            "verified": verified is True,
            "degraded": verified is not True,
        }

    async def _handle_tab_rename(self, args: Dict[str, Any]) -> Dict[str, Any]:
        session = self._resolve_session(args.get("session_name"))
        tab_id = cast(int, args["tab_id"])
        name = cast(str, args["tab_name"])
        tabs = self._list_tabs_checked(session)
        target = next(
            (item for item in (tabs or []) if item.get("tab_id") == tab_id),
            None,
        )
        if tabs is None or target is None:
            raise MCPError(
                code=(
                    ErrorCode.INTERNAL_ERROR
                    if tabs is None
                    else ErrorCode.WORKSPACE_NOT_FOUND
                ),
                message="Zellij Tab not found or unavailable: {}/{}".format(session, tab_id),
            )
        changed = target.get("name") != name
        if changed and not self.zellij.rename_tab(session, tab_id, name):
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Failed to rename zellij Tab: {}/{}".format(session, tab_id),
            )
        tabs_after = self._list_tabs_checked(session)
        renamed = next(
            (item for item in (tabs_after or []) if item.get("tab_id") == tab_id),
            None,
        )
        if tabs_after is not None and (renamed is None or renamed.get("name") != name):
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Zellij Tab rename postcondition failed",
            )
        return {
            "renamed": True,
            "changed": changed,
            "session": session,
            "tab_id": tab_id,
            "previous_name": target.get("name"),
            "tab": renamed or dict(target, name=name),
            "verified": tabs_after is not None,
            "degraded": tabs_after is None,
        }

    async def _handle_tab_close(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not args.get("force", False):
            raise MCPError(
                code=ErrorCode.PERMISSION_DENIED,
                message="Closing a zellij Tab requires force=true",
            )
        session = self._resolve_session(args.get("session_name"))
        tab_id = cast(int, args["tab_id"])
        tabs = self._list_tabs_checked(session)
        panes = self._list_panes_checked(session, include_plugins=True)
        target = next(
            (item for item in (tabs or []) if item.get("tab_id") == tab_id),
            None,
        )
        if tabs is None or panes is None:
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Unable to enumerate zellij Tab before close",
            )
        if target is None:
            raise MCPError(
                code=ErrorCode.WORKSPACE_NOT_FOUND,
                message="Zellij Tab not found: {}/{}".format(session, tab_id),
            )
        target_panes = [item for item in panes if item.get("tab_id") == tab_id]
        if not target_panes:
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Unable to confirm pane membership for zellij Tab",
            )
        current = self._current_mcp_identity_for_close()
        if current is not None and session == current["session"]:
            if not any(item.get("pane_id") == current["pane_id"] for item in panes):
                raise MCPError(
                    code=ErrorCode.PERMISSION_DENIED,
                    message="Refusing to close a Tab because the current MCP pane is unavailable",
                )
            if any(item.get("pane_id") == current["pane_id"] for item in target_panes):
                raise MCPError(
                    code=ErrorCode.PERMISSION_DENIED,
                    message="Refusing to close the Tab containing the current MCP pane",
                )
        if not self.zellij.close_tab(session, tab_id):
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Failed to close zellij Tab: {}/{}".format(session, tab_id),
            )
        tabs_after = self._list_tabs_checked(session)
        session_presence = self.zellij.session_presence(session)
        if session_presence is None:
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Zellij Tab close postcondition is unknown",
            )
        session_closed = session_presence is False
        if not session_closed and (
            tabs_after is None or any(item.get("tab_id") == tab_id for item in tabs_after)
        ):
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Zellij Tab close postcondition failed or is unknown",
            )
        return {
            "closed": True,
            "session": session,
            "tab_id": tab_id,
            "tab": target,
            "pane_ids": [item.get("pane_id") for item in target_panes],
            "resources": ["zellij_session" if session_closed else "zellij_tab"],
            "verified": True,
            "session_closed": session_closed,
        }

    async def _handle_pane_write_text(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return self._write_pane_input(args, "text")

    async def _handle_pane_send_key(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return self._write_pane_input(args, "key")

    def _write_pane_input(
        self,
        args: Dict[str, Any],
        kind: str,
    ) -> Dict[str, Any]:
        target = self._resolve_live_terminal_pane(
            args.get("session_name"),
            cast(str, args["pane_id"]),
        )
        if kind == "text":
            accepted = self.zellij.write_to_pane(
                cast(str, args["text"]),
                pane_id=target["pane_id"],
                session=target["session"],
            )
        else:
            accepted = self.zellij.send_keys(
                cast(str, args["key"]),
                pane_id=target["pane_id"],
                session=target["session"],
            )
        if not accepted:
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="zellij did not accept pane input",
            )
        return {
            "written": True,
            "accepted": True,
            "session": target["session"],
            "pane_id": target["pane_id"],
            "kind": kind,
            "bytes": len(cast(str, args.get("text", "")).encode("utf-8")),
            "completion_verified": False,
        }

    async def _handle_pane_screen(self, args: Dict[str, Any]) -> Dict[str, Any]:
        target = self._resolve_live_terminal_pane(
            args.get("session_name"),
            cast(str, args["pane_id"]),
        )
        full = bool(args.get("full", False))
        ansi = bool(args.get("ansi", False))
        text = self.zellij.capture_pane(
            pane_id=target["pane_id"],
            session=target["session"],
            full=full,
            ansi=ansi,
            max_bytes=(self.MAX_PANE_SCREEN_CHARS + 1) * 4,
        )
        if text is None:
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Unable to dump zellij pane screen",
            )
        capture_truncated = bool(text.get("truncated"))
        screen_text = cast(str, text.get("text", ""))
        if not ansi:
            screen_text = self.ANSI_ESCAPE_RE.sub("", screen_text)
        truncated = capture_truncated or len(screen_text) > self.MAX_PANE_SCREEN_CHARS
        if truncated:
            screen_text = screen_text[-self.MAX_PANE_SCREEN_CHARS :]
        return {
            "session": target["session"],
            "pane_id": target["pane_id"],
            "text": screen_text,
            "full": full,
            "ansi": ansi,
            "truncated": truncated,
            "source": "zellij_dump_screen",
        }

    async def _handle_pane_close(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not args.get("force", False):
            raise MCPError(
                code=ErrorCode.PERMISSION_DENIED,
                message="Closing a zellij pane requires force=true",
            )
        target = self._resolve_live_terminal_pane(
            args.get("session_name"),
            cast(str, args["pane_id"]),
        )
        current = self._current_mcp_identity_for_close()
        if current is not None and target["session"] == current["session"]:
            panes_before = self._list_panes_checked(
                target["session"],
                include_plugins=True,
            )
            if panes_before is None or not any(
                item.get("pane_id") == current["pane_id"] for item in panes_before
            ):
                raise MCPError(
                    code=ErrorCode.PERMISSION_DENIED,
                    message="Refusing to close a pane because the current MCP pane is unavailable",
                )
            if target["pane_id"] == current["pane_id"]:
                raise MCPError(
                    code=ErrorCode.PERMISSION_DENIED,
                    message="Refusing to close the current MCP pane",
                )
        if not self.zellij.close_pane(
            target["pane_id"],
            session=target["session"],
        ):
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Failed to close zellij pane",
            )
        presence = self.zellij.session_presence(target["session"])
        if presence is None:
            raise MCPError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Zellij pane close postcondition is unknown",
            )
        session_closed = presence is False
        if presence is True:
            panes_after = self._list_panes_checked(
                target["session"],
                include_plugins=True,
            )
            if panes_after is None:
                raise MCPError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message="Zellij pane close postcondition is unknown",
                )
            if any(
                item.get("pane_id") == target["pane_id"] for item in panes_after
            ):
                raise MCPError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message="Zellij pane close postcondition failed",
                )
        return {
            "closed": True,
            "verified": True,
            "session": target["session"],
            "pane_id": target["pane_id"],
            "session_closed": session_closed,
            "resources": ["zellij_session" if session_closed else "zellij_pane"],
        }
