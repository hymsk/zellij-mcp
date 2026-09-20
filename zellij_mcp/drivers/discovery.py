"""Pure normalization helpers for zellij discovery output."""

import re
from typing import Any, Dict, List, Optional, Set


class ZellijDiscovery:
    """Parse zellij session, Tab and pane data without performing I/O."""

    def parse_active_sessions(self, text: str) -> List[str]:
        """Exclude zellij's exited, resurrectable session records."""
        sessions = []  # type: List[str]
        seen: Set[str] = set()
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or "(EXITED" in line.upper():
                continue
            if " [Created " in line:
                name = line.split(" [Created ", 1)[0].strip()
            else:
                name = re.sub(
                    r"\s+\(current\)\s*$",
                    "",
                    line,
                    flags=re.IGNORECASE,
                ).strip()
            if name and name not in seen:
                seen.add(name)
                sessions.append(name)
        return sessions

    def normalize_tabs(self, payload: Any) -> List[Dict[str, Any]]:
        """Normalize zellij tab JSON across compatible output variants."""
        if isinstance(payload, dict):
            payload = payload.get("tabs")
        if not isinstance(payload, list):
            return []

        tabs = []  # type: List[Dict[str, Any]]
        seen: Set[int] = set()
        for value in payload:
            if not isinstance(value, dict):
                continue
            tab_id = self.non_negative_int(value.get("tab_id", value.get("id")))
            if tab_id is None or tab_id in seen:
                continue
            seen.add(tab_id)
            native_active = value.get("active") is True
            tabs.append({
                "tab_id": tab_id,
                "position": self.non_negative_int(value.get("position")),
                "name": self.text_value(value.get("name")),
                "active": native_active,
                "active_source": "native" if native_active else "unavailable",
                "is_fullscreen_active": bool(value.get("is_fullscreen_active")),
                "is_sync_panes_active": bool(value.get("is_sync_panes_active")),
                "are_floating_panes_visible": bool(
                    value.get("are_floating_panes_visible")
                ),
                "selectable_tiled_panes_count": self.non_negative_int(
                    value.get("selectable_tiled_panes_count")
                ),
                "selectable_floating_panes_count": self.non_negative_int(
                    value.get("selectable_floating_panes_count")
                ),
                "viewport_rows": self.non_negative_int(value.get("viewport_rows")),
                "viewport_columns": self.non_negative_int(
                    value.get("viewport_columns")
                ),
                "display_area_rows": self.non_negative_int(
                    value.get("display_area_rows")
                ),
                "display_area_columns": self.non_negative_int(
                    value.get("display_area_columns")
                ),
                "has_bell_notification": bool(value.get("has_bell_notification")),
                "is_flashing_bell": bool(value.get("is_flashing_bell")),
            })
        return sorted(
            tabs,
            key=lambda item: (
                item.get("position") is None,
                item.get("position") if item.get("position") is not None else 0,
                item.get("tab_id"),
            ),
        )

    def non_negative_int(self, value: Any) -> Optional[int]:
        """Normalize an integer-like zellij field without accepting booleans."""
        if isinstance(value, int) and type(value) is not bool and value >= 0:
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    def payload_has_empty_panes(self, payload: Any) -> bool:
        """Recognize known pane containers that explicitly contain no panes."""
        if not isinstance(payload, dict):
            return False
        if payload.get("panes") == []:
            return True
        tabs = payload.get("tabs")
        return isinstance(tabs, list) and bool(tabs) and all(
            isinstance(tab, dict) and tab.get("panes") == [] for tab in tabs
        )

    def normalize_panes(self, payload: Any) -> List[Dict[str, Any]]:
        """Normalize zellij's JSON pane output across versions."""
        panes = []  # type: List[Dict[str, Any]]
        seen: Set[str] = set()

        def visit(value: Any) -> None:
            if isinstance(value, list):
                for item in value:
                    visit(item)
                return
            if not isinstance(value, dict):
                return

            pane_id = self.pane_id_from_dict(value) if self.looks_like_pane(value) else None
            if pane_id and pane_id not in seen:
                seen.add(pane_id)
                is_plugin = bool(value.get("is_plugin")) or pane_id.startswith("plugin_")
                panes.append({
                    "pane_id": pane_id,
                    "is_plugin": is_plugin,
                    "is_focused": bool(value.get("is_focused")),
                    "is_fullscreen": bool(value.get("is_fullscreen")),
                    "is_floating": bool(value.get("is_floating")),
                    "is_suppressed": bool(value.get("is_suppressed")),
                    "is_held": bool(value.get("is_held")),
                    "is_selectable": bool(value.get("is_selectable", True)),
                    "exited": bool(value.get("exited")),
                    "exit_status": value.get("exit_status"),
                    "title": self.text_value(value.get("title")),
                    "command": self.first_text(
                        value,
                        "pane_command",
                        "terminal_command",
                        "command",
                    ),
                    "cwd": self.first_text(value, "pane_cwd", "cwd"),
                    "state": self.pane_state(value),
                    "tab_id": self.non_negative_int(value.get("tab_id")),
                    "tab_position": self.non_negative_int(value.get("tab_position")),
                    "tab_name": self.text_value(value.get("tab_name")),
                    "pane_x": value.get("pane_x"),
                    "pane_y": value.get("pane_y"),
                    "pane_rows": value.get("pane_rows"),
                    "pane_columns": value.get("pane_columns"),
                    "pane_content_rows": value.get("pane_content_rows"),
                    "pane_content_columns": value.get("pane_content_columns"),
                })

            for child in value.values():
                if isinstance(child, (dict, list)):
                    visit(child)

        visit(payload)
        return sorted(panes, key=self.pane_sort_key)

    def looks_like_pane(self, value: Dict[str, Any]) -> bool:
        """Avoid treating nested tab or geometry dictionaries as panes."""
        if "pane_id" in value:
            return True
        if "id" not in value:
            return False
        pane_keys = (
            "is_plugin",
            "pane_command",
            "terminal_command",
            "plugin_url",
            "is_focused",
            "is_floating",
            "is_suppressed",
            "pane_rows",
        )
        return any(key in value for key in pane_keys)

    def pane_id_from_dict(self, value: Dict[str, Any]) -> Optional[str]:
        raw_id = value.get("pane_id") if "pane_id" in value else value.get("id")
        if raw_id is None:
            return None
        return self.normalize_pane_id(str(raw_id), is_plugin=bool(value.get("is_plugin")))

    def first_text(self, value: Dict[str, Any], *keys: str) -> str:
        for key in keys:
            text = self.text_value(value.get(key))
            if text:
                return text
        return ""

    def text_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            return " ".join(str(item) for item in value)
        return str(value)

    def pane_state(self, value: Dict[str, Any]) -> str:
        explicit = value.get("state") or value.get("pane_state")
        if explicit:
            return str(explicit)
        if value.get("exited"):
            return "exited"
        if value.get("is_held"):
            return "held"
        if value.get("is_suppressed"):
            return "suppressed"
        return "running"

    def pane_sort_key(self, pane: Dict[str, Any]) -> Any:
        pane_id = pane.get("pane_id", "")
        match = re.search(r"(\d+)$", pane_id)
        numeric_id = int(match.group(1)) if match else -1
        tab_position = pane.get("tab_position")
        if not isinstance(tab_position, int):
            tab_position = -1
        return (
            tab_position,
            1 if pane.get("is_plugin") else 0,
            numeric_id,
            pane_id,
        )

    def normalize_pane_id(self, pane_id: str, is_plugin: bool = False) -> str:
        """Normalize numeric pane ids to zellij terminal_<id> form."""
        stripped = pane_id.strip()
        if stripped.isdigit():
            prefix = "plugin" if is_plugin else "terminal"
            return "{}_{}".format(prefix, stripped)
        return stripped
