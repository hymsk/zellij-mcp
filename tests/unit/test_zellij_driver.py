"""Direct zellij action construction and bounded screen tests."""

import json
import subprocess
from pathlib import Path

import pytest

from zellij_mcp.drivers.zellij import (
    ZellijDriver,
    ZellijMutationOutcomeUnknownError,
)


def completed(argv, stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess(
        argv,
        returncode,
        stdout=stdout,
        stderr=stderr,
    )


def driver_with_path():
    driver = ZellijDriver()
    driver.zellij_path = "/usr/bin/zellij"
    return driver


def test_write_chars_uses_option_terminator(monkeypatch):
    driver = driver_with_path()
    calls = []

    def fake_run(argv, **unused_kwargs):
        calls.append(argv)
        return completed(argv)

    monkeypatch.setattr(driver, "_run", fake_run)

    assert driver.write_to_pane("--help", pane_id="terminal_7", session="main")
    assert calls == [[
        "/usr/bin/zellij",
        "--session",
        "main",
        "action",
        "write-chars",
        "-p",
        "terminal_7",
        "--",
        "--help",
    ]]


@pytest.mark.parametrize(
    "public_key,zellij_key",
    [("Ctrl-C", "Ctrl c"), ("Ctrl-D", "Ctrl d"), ("Escape", "Esc")],
)
def test_send_keys_maps_public_names_to_one_zellij_argument(
    monkeypatch,
    public_key,
    zellij_key,
):
    driver = driver_with_path()
    calls = []
    monkeypatch.setattr(
        driver,
        "_run",
        lambda argv, **unused_kwargs: calls.append(argv) or completed(argv),
    )

    assert driver.send_keys(public_key, pane_id="terminal_7", session="main")
    assert calls[0][-1] == zellij_key
    assert calls[0][-2] == "terminal_7"


def test_capture_pane_reads_only_the_bounded_file_tail(monkeypatch):
    driver = driver_with_path()

    def fake_run(argv, **unused_kwargs):
        dump_path = Path(argv[argv.index("--path") + 1])
        dump_path.write_bytes(b"abcdefgh")
        return completed(argv)

    monkeypatch.setattr(driver, "_run", fake_run)

    result = driver.capture_pane(
        pane_id="terminal_7",
        session="main",
        full=True,
        ansi=True,
        max_bytes=5,
    )

    assert result == {"text": "defgh", "truncated": True}


def test_capture_pane_uses_a_private_temporary_directory(monkeypatch):
    driver = driver_with_path()
    observed = {}

    def fake_run(argv, **unused_kwargs):
        dump_path = Path(argv[argv.index("--path") + 1])
        observed["directory_mode"] = dump_path.parent.stat().st_mode & 0o777
        observed["exists_before_action"] = dump_path.exists()
        dump_path.write_text("screen", encoding="utf-8")
        return completed(argv)

    monkeypatch.setattr(driver, "_run", fake_run)

    result = driver.capture_pane(pane_id="terminal_7", session="main")

    assert result == {"text": "screen", "truncated": False}
    assert observed == {"directory_mode": 0o700, "exists_before_action": False}


def test_direct_pane_capability_requires_dump_screen_options(monkeypatch):
    driver = driver_with_path()

    def fake_run(argv, **unused_kwargs):
        action = argv[2]
        output = "--pane-id"
        if action == "dump-screen":
            output += " --ansi"
        return completed(argv, stdout=output)

    monkeypatch.setattr(driver, "_run", fake_run)

    assert driver.supports_direct_pane_io() is False


def test_basic_helpers_and_environment(monkeypatch):
    driver = driver_with_path()
    monkeypatch.setenv("ZELLIJ", "0")
    monkeypatch.setenv("ZELLIJ_SESSION_NAME", "main")
    monkeypatch.setenv("ZELLIJ_PANE_ID", "7")

    assert driver.is_available() is True
    assert driver.is_inside_zellij() is True
    assert driver.get_current_session() == "main"
    assert driver.get_current_pane_id() == "terminal_7"
    assert driver.normalize_pane_id(" 8 ") == "terminal_8"
    assert driver.normalize_pane_id("8", is_plugin=True) == "plugin_8"
    assert driver.normalize_pane_id("terminal_8") == "terminal_8"
    assert driver.action_command("main", "list-panes") == [
        "/usr/bin/zellij",
        "--session",
        "main",
        "action",
        "list-panes",
    ]


def test_capability_checks(monkeypatch):
    driver = driver_with_path()

    def fake_run(argv, **unused_kwargs):
        if argv[1:3] == ["attach", "--help"]:
            return completed(argv, stdout="--create-background")
        if argv[1:3] == ["action", "--help"]:
            return completed(
                argv,
                stdout=(
                    "list-tabs new-tab go-to-tab-by-id rename-tab-by-id "
                    "close-tab-by-id"
                ),
            )
        if argv[1:4] == ["action", "new-pane", "--help"]:
            return completed(argv, stdout="--tab-id")
        if argv[1] == "action" and argv[-1] == "--help":
            output = "--pane-id"
            if argv[2] == "dump-screen":
                output += " --ansi --path"
            return completed(argv, stdout=output)
        raise AssertionError(argv)

    monkeypatch.setattr(driver, "_run", fake_run)

    assert driver.supports_background_create() is True
    assert driver.supports_stable_tab_control() is True
    assert driver.supports_direct_pane_io() is True


def test_session_listing_requires_no_formatting_output(monkeypatch):
    driver = driver_with_path()
    calls = []

    def fake_run(argv, **unused_kwargs):
        calls.append(argv)
        return completed(argv, stdout="main\nbuild\n")

    monkeypatch.setattr(driver, "_run", fake_run)

    assert driver.list_sessions_checked() == ["main", "build"]
    assert calls[-1][-1] == "--no-formatting"
    assert driver._parse_active_sessions(
        "main [Created now] (current)\nold [Created then] (EXITED)\nmain\nbuild\n"
    ) == ["main", "build"]


def test_session_presence_and_empty_markers(monkeypatch):
    driver = driver_with_path()
    monkeypatch.setattr(
        driver,
        "_run",
        lambda argv, **unused_kwargs: completed(
            argv,
            returncode=1,
            stderr="No active zellij sessions",
        ),
    )

    assert driver.list_sessions() == []
    assert driver.session_presence("main") is False
    assert driver.is_running() is False


def test_layout_and_background_session_creation(monkeypatch, tmp_path):
    driver = driver_with_path()
    calls = []
    monkeypatch.setattr(driver, "supports_background_create", lambda: True)
    monkeypatch.setattr(driver, "session_presence", lambda unused_name: False)
    monkeypatch.setattr(driver, "close_startup_plugin_panes", lambda name: calls.append(name))
    monkeypatch.setattr(driver, "_wait_for_terminal_pane", lambda unused_name: "terminal_0")

    def fake_run(argv, **unused_kwargs):
        calls.append(argv)
        return completed(argv)

    monkeypatch.setattr(driver, "_run", fake_run)
    monkeypatch.setattr("zellij_mcp.drivers.zellij.time.sleep", lambda unused: None)

    layout = driver.layout_for_command(["/bin/sh", "-c", "echo hi"], str(tmp_path))
    assert 'pane command="/bin/sh"' in layout
    assert 'args "-c" "echo hi"' in layout
    with pytest.raises(ValueError):
        driver.layout_for_command([], str(tmp_path))

    workspace = driver.create_session_with_command(
        "build",
        cwd=str(tmp_path),
        command=["/bin/sh", "-c", "echo hi"],
    )
    assert workspace is not None
    assert workspace.dict() == {"type": "session", "session": "build", "pane": "terminal_0"}
    assert calls[-1] == "build"


def test_create_session_rejects_unknown_or_existing_presence(monkeypatch):
    driver = driver_with_path()
    monkeypatch.setattr(driver, "supports_background_create", lambda: True)
    monkeypatch.setattr(driver, "session_presence", lambda unused_name: None)
    assert driver.create_session_with_command("build", command=["sh"]) is None


def test_background_session_timeout_is_reconciled(monkeypatch):
    driver = driver_with_path()
    presence = iter([False, True])
    monkeypatch.setattr(driver, "supports_background_create", lambda: True)
    monkeypatch.setattr(driver, "session_presence", lambda unused_name: next(presence))
    monkeypatch.setattr(driver, "_run", lambda argv, **unused_kwargs: None)
    monkeypatch.setattr(driver, "_wait_for_terminal_pane", lambda unused_name: "terminal_0")
    monkeypatch.setattr(driver, "close_startup_plugin_panes", lambda unused_name: None)
    monkeypatch.setattr("zellij_mcp.drivers.zellij.time.sleep", lambda unused: None)

    workspace = driver.create_session_with_command("build", command=["sh"])

    assert workspace is not None
    assert workspace.session == "build"
    monkeypatch.setattr(driver, "session_presence", lambda unused_name: True)
    assert driver.create_session_with_command("build", command=["sh"]) is None


def test_background_session_keeps_layout_until_pane_is_discovered(monkeypatch, tmp_path):
    driver = driver_with_path()
    layout_paths = []
    attach_commands = []
    monkeypatch.setattr(driver, "supports_background_create", lambda: True)
    monkeypatch.setattr(driver, "session_presence", lambda unused_name: False)
    monkeypatch.setattr(driver, "close_startup_plugin_panes", lambda unused_name: None)
    def discover(unused_name):
        layout_path = next(
            item
            for item in attach_commands[-1]
            if item.endswith(".kdl")
        )
        layout_paths.append(layout_path)
        assert Path(layout_path).exists()
        return "terminal_7"

    def remember_run(argv, **unused_kwargs):
        attach_commands.append(argv)
        return completed(argv)

    monkeypatch.setattr(driver, "_run", remember_run)
    monkeypatch.setattr(driver, "_wait_for_terminal_pane", discover)

    workspace = driver.create_session_with_command(
        "build",
        cwd=str(tmp_path),
        command=["sh"],
    )

    assert workspace is not None and workspace.pane == "terminal_7"
    assert len(layout_paths) == 1
    assert not Path(layout_paths[0]).exists()


def test_background_session_without_terminal_pane_is_rolled_back(monkeypatch):
    driver = driver_with_path()
    monkeypatch.setattr(driver, "supports_background_create", lambda: True)
    monkeypatch.setattr(driver, "session_presence", lambda unused_name: False)
    monkeypatch.setattr(driver, "_run", lambda argv, **unused_kwargs: completed(argv))
    monkeypatch.setattr(driver, "_wait_for_terminal_pane", lambda unused_name: None)
    monkeypatch.setattr(driver, "close_session", lambda unused_name: True)

    assert driver.create_session_with_command("build", command=["sh"]) is None


def test_background_session_failed_rollback_has_unknown_outcome(monkeypatch):
    driver = driver_with_path()
    monkeypatch.setattr(driver, "supports_background_create", lambda: True)
    monkeypatch.setattr(driver, "session_presence", lambda unused_name: False)
    monkeypatch.setattr(driver, "_run", lambda argv, **unused_kwargs: completed(argv))
    monkeypatch.setattr(driver, "_wait_for_terminal_pane", lambda unused_name: None)
    monkeypatch.setattr(driver, "close_session", lambda unused_name: False)

    with pytest.raises(
        ZellijMutationOutcomeUnknownError,
        match="terminal pane could not be discovered",
    ):
        driver.create_session_with_command("build", command=["sh"])


def test_normalize_tabs(monkeypatch):
    driver = driver_with_path()
    tabs = driver._normalize_tabs({
        "tabs": [
            {"id": "7", "position": "1", "name": "Build"},
            {"tab_id": 2, "position": 0, "name": ["Main"], "active": False},
            {"id": -1},
            {"id": 7},
            "ignored",
        ]
    })
    assert [item["tab_id"] for item in tabs] == [2, 7]
    assert tabs[0]["name"] == "Main"
    assert driver._non_negative_int(True) is None
    assert driver._non_negative_int("9") == 9


def test_list_tabs_and_tab_actions(monkeypatch):
    driver = driver_with_path()
    payloads = [
        json.dumps([{"tab_id": 0, "position": 0, "active": True}]),
        "8",
    ]
    calls = []

    def fake_run(argv, **unused_kwargs):
        calls.append(argv)
        if argv[-1] in {"--all", "--panes", "--json"}:
            return completed(argv, stdout=payloads[0])
        if "new-tab" in argv:
            return completed(argv, stdout=payloads[1])
        return completed(argv)

    monkeypatch.setattr(driver, "_run", fake_run)

    tabs = driver.list_tabs_checked("main")
    assert tabs is not None and tabs[0]["active"] is True
    assert driver.create_tab(
        "main",
        name="Build",
        cwd="/work",
        command=["sh"],
    ) == 8
    assert driver.focus_tab("main", 8) is True
    assert driver.rename_tab("main", 8, "Logs") is True
    assert driver.close_tab("main", 8) is True
    assert any(
        "--name" in argv and "--no-focus" in argv and "--" in argv
        for argv in calls
    )


def test_create_tab_finds_new_id_when_stdout_is_empty(monkeypatch):
    driver = driver_with_path()
    tab_lists = [
        [{"tab_id": 0}],
        [{"tab_id": 0}, {"tab_id": 4}],
    ]
    monkeypatch.setattr(driver, "list_tabs_checked", lambda unused_session: tab_lists.pop(0))
    monkeypatch.setattr(driver, "_run", lambda argv, **unused_kwargs: completed(argv))

    assert driver.create_tab("main") == 4


def test_normalize_nested_panes_and_summary(monkeypatch):
    driver = driver_with_path()
    payload = {
        "tabs": [{
            "panes": [
                {
                    "id": 1,
                    "tab_id": "2",
                    "tab_position": 1,
                    "title": "Shell",
                    "pane_command": ["bash", "-l"],
                    "pane_cwd": "/work",
                    "is_focused": True,
                    "pane_rows": 24,
                },
                {
                    "pane_id": "plugin_0",
                    "is_plugin": True,
                    "is_suppressed": True,
                },
            ]
        }]
    }
    panes = driver._normalize_panes(payload)
    by_id = {item["pane_id"]: item for item in panes}
    assert set(by_id) == {"terminal_1", "plugin_0"}
    assert by_id["terminal_1"]["command"] == "bash -l"
    assert by_id["terminal_1"]["state"] == "running"
    assert by_id["plugin_0"]["state"] == "suppressed"
    monkeypatch.setattr(driver, "list_panes_checked", lambda *args, **kwargs: panes)
    monkeypatch.setattr(driver, "get_current_session", lambda: "main")
    monkeypatch.setattr(driver, "get_current_pane_id", lambda: "terminal_1")

    summary = driver.get_session_summary("main", include_plugins=True)
    assert summary is not None
    assert summary["terminal_pane_count"] == 1
    assert summary["plugin_pane_count"] == 1
    summarized = {item["pane_id"]: item for item in summary["panes"]}
    assert summarized["terminal_1"]["is_current"] is True


def test_list_panes_json_and_empty_paths(monkeypatch):
    driver = driver_with_path()
    results = [
        completed([], stdout="[]"),
    ]
    monkeypatch.setattr(driver, "_run", lambda argv, **unused_kwargs: results.pop(0))

    assert driver.list_panes_checked("main", include_plugins=True) == []


def test_list_panes_rejects_nonempty_unparseable_output(monkeypatch):
    driver = driver_with_path()
    monkeypatch.setattr(
        driver,
        "_run",
        lambda argv, **unused_kwargs: completed(argv, stdout="unexpected output"),
    )

    assert driver.list_panes_checked("main", include_plugins=True) is None


def test_list_panes_rejects_empty_success_output(monkeypatch):
    driver = driver_with_path()
    monkeypatch.setattr(
        driver,
        "_run",
        lambda argv, **unused_kwargs: completed(argv, stdout=""),
    )

    assert driver.list_panes_checked("main", include_plugins=True) is None


def test_create_pane_does_not_mutate_when_discovery_is_unknown(monkeypatch):
    driver = driver_with_path()
    calls = []
    monkeypatch.setattr(driver, "list_panes_checked", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        driver,
        "_run",
        lambda argv, **unused_kwargs: calls.append(argv) or completed(argv),
    )

    assert driver.create_pane(session="main", command=["sh"]) is None
    assert calls == []


def test_create_pane_timeout_is_reconciled_by_discovery(monkeypatch):
    driver = driver_with_path()
    panes = [
        [{"pane_id": "terminal_0", "is_plugin": False, "title": "root"}],
        [
            {"pane_id": "terminal_0", "is_plugin": False, "title": "root"},
            {"pane_id": "terminal_3", "is_plugin": False, "title": "named"},
        ],
    ]
    monkeypatch.setattr(
        driver,
        "list_panes_checked",
        lambda unused_session, include_plugins: panes.pop(0),
    )
    monkeypatch.setattr(driver, "_run", lambda argv, **unused_kwargs: None)

    workspace = driver.create_pane(
        session="main",
        name="named",
        command=["sh"],
    )

    assert workspace is not None
    assert workspace.pane == "terminal_3"


def test_create_pane_waits_for_asynchronous_discovery(monkeypatch):
    driver = driver_with_path()
    panes = [
        [{"pane_id": "terminal_0", "is_plugin": False, "title": "root"}],
        [{"pane_id": "terminal_0", "is_plugin": False, "title": "root"}],
        [
            {"pane_id": "terminal_0", "is_plugin": False, "title": "root"},
            {"pane_id": "terminal_4", "is_plugin": False, "title": "named"},
        ],
    ]
    monkeypatch.setattr(
        driver,
        "list_panes_checked",
        lambda unused_session, include_plugins: panes.pop(0),
    )
    monkeypatch.setattr(driver, "_run", lambda argv, **unused_kwargs: completed(argv))
    monkeypatch.setattr("zellij_mcp.drivers.zellij.time.sleep", lambda unused: None)

    workspace = driver.create_pane(
        session="main",
        name="named",
        command=["sh"],
    )

    assert workspace is not None and workspace.pane == "terminal_4"


def test_relative_cwd_is_resolved_once_for_tab_and_pane(monkeypatch, tmp_path):
    driver = driver_with_path()
    monkeypatch.chdir(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    calls = []
    tabs = [[{"tab_id": 0}], [{"tab_id": 0}, {"tab_id": 4}]]
    panes = [[{"pane_id": "terminal_0", "is_plugin": False}]]
    monkeypatch.setattr(driver, "list_tabs_checked", lambda unused_session: tabs.pop(0))
    monkeypatch.setattr(
        driver,
        "list_panes_checked",
        lambda unused_session, include_plugins: panes[0],
    )

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs.get("cwd")))
        if "new-tab" in argv:
            return completed(argv, stdout="4")
        return completed(argv, stdout="terminal_3")

    monkeypatch.setattr(driver, "_run", fake_run)

    assert driver.create_tab("main", cwd="work") == 4
    assert driver.create_pane("main", cwd="work", command=["sh"]) is not None
    for argv, process_cwd in calls:
        assert process_cwd == str(work)
        assert argv[argv.index("--cwd") + 1] == str(work)


def test_create_close_and_key_actions(monkeypatch):
    driver = driver_with_path()
    panes = [
        [{"pane_id": "terminal_0", "is_plugin": False}],
        [
            {"pane_id": "terminal_0", "is_plugin": False},
            {"pane_id": "terminal_3", "is_plugin": False, "title": "named"},
        ],
    ]
    monkeypatch.setattr(
        driver,
        "list_panes_checked",
        lambda unused_session, include_plugins: panes.pop(0) if panes else [],
    )
    calls = []

    def fake_run(argv, **unused_kwargs):
        calls.append(argv)
        if "new-pane" in argv:
            return completed(argv, stdout="terminal_3")
        return completed(argv)

    monkeypatch.setattr(driver, "_run", fake_run)

    workspace = driver.create_pane(
        session="main",
        name="named",
        cwd="/work",
        command=["sh"],
        tab_id=2,
    )
    assert workspace is not None and workspace.pane == "terminal_3"
    assert driver.send_keys("Enter", pane_id="terminal_3", session="main") is True
    assert driver.write_to_pane(
        "status",
        pane_id="terminal_3",
        session="main",
        enter=True,
    ) is True
    assert driver.close_pane("terminal_3", session="main") is True
    assert driver.close_session("main") is True
    assert any("--tab-id" in argv for argv in calls)


def test_doctor_reports_healthy_runtime(monkeypatch):
    driver = driver_with_path()
    monkeypatch.setenv("ZELLIJ", "0")
    monkeypatch.setenv("ZELLIJ_SESSION_NAME", "main")
    monkeypatch.setenv("ZELLIJ_PANE_ID", "0")
    monkeypatch.setattr(driver, "is_running", lambda: True)
    monkeypatch.setattr(driver, "supports_background_create", lambda: True)
    monkeypatch.setattr(driver, "supports_stable_tab_control", lambda: True)
    monkeypatch.setattr(driver, "supports_direct_pane_io", lambda: True)
    monkeypatch.setattr(driver, "list_sessions", lambda: ["main"])
    monkeypatch.setattr(
        driver,
        "get_session_summary",
        lambda *args, **kwargs: {"session": "main"},
    )
    monkeypatch.setattr(
        driver,
        "_run",
        lambda argv, **unused_kwargs: completed(argv, stdout="zellij 0.44.3"),
    )

    result = driver.doctor()
    assert result["version"] == "zellij 0.44.3"
    assert result["supports_direct_pane_io"] is True
    assert result["current_workspace"] == {"session": "main"}
    assert result["warnings"] == []
