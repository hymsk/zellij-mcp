#!/usr/bin/env python3
"""Manual MCP integration probe for zellij pane creation."""

import argparse
import asyncio
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from zellij_mcp.server.main import ZellijMCPServer  # noqa: E402


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Create a zellij pane through MCP and clean it up by default.",
    )
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=2.0,
        help="Seconds to keep the pane visible before cleanup.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Leave the created pane open for manual inspection.",
    )
    return parser.parse_args()


async def run_probe(hold_seconds: float, keep: bool) -> int:
    """Create one pane, report its identity, and normally close it."""
    server = ZellijMCPServer()

    doctor = await server.call_tool("zellij_mcp_doctor", {})
    if doctor.get("error"):
        print("zellij_mcp_doctor failed: {}".format(doctor.get("message")), file=sys.stderr)
        return 1
    capabilities = doctor.get("result", {}).get("capabilities", {})
    print("zellij available: {}".format(capabilities.get("zellij", False)))
    print("inside zellij: {}".format(capabilities.get("inside_zellij", False)))

    created = await server.call_tool(
        "workspace_create",
        {
            "request_id": "integration-create-pane",
            "command": [
                "bash",
                "-lc",
                "printf 'Zellij MCP pane probe\n'; exec bash",
            ],
            "workspace_type": "new-pane",
            "cwd": "/tmp",
        },
    )
    if created.get("error"):
        print("workspace_create failed: {}".format(created.get("message")), file=sys.stderr)
        return 1

    info = created.get("result", {})
    pane_id = info.get("pane_id")
    session = info.get("session")
    print("Pane ID: {}".format(pane_id))
    print("Session: {}".format(session))

    if keep:
        print("Pane retained because --keep was supplied.")
        return 0

    await asyncio.sleep(max(hold_seconds, 0.0))
    closed = await server.call_tool(
        "pane_close",
        {
            "session_name": session,
            "pane_id": pane_id,
            "force": True,
        },
    )
    if closed.get("error"):
        print("pane_close failed: {}".format(closed.get("message")), file=sys.stderr)
        return 1
    print("Pane closed.")
    return 0


def main() -> int:
    """Run the integration probe."""
    args = parse_args()
    return asyncio.run(run_probe(args.hold_seconds, args.keep))


if __name__ == "__main__":
    sys.exit(main())
