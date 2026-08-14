"""Host-filtered zellij context recovery tests."""

import os

import zellij_mcp.cli as cli_module
from zellij_mcp.host_context import (
    ZELLIJ_CONTEXT_KEYS,
    _parse_process_stat,
    _parse_process_uid,
    _read_linux_process,
    restore_zellij_context,
)


def process_context(ppid, uid, environment):
    """Build one injected Linux process context."""
    return {
        "ppid": ppid,
        "uid": uid,
        "environment": dict(environment),
    }


def test_restore_preserves_existing_values_and_only_imports_allowlist():
    environment = {
        "ZELLIJ": "99",
        "SECRET_TOKEN": "child-secret",
    }
    contexts = {
        42: process_context(
            1,
            1000,
            {
                "ZELLIJ": "0",
                "ZELLIJ_SESSION_NAME": "current-session",
                "ZELLIJ_PANE_ID": "7",
                "XDG_RUNTIME_DIR": "/run/user/1000",
                "SECRET_TOKEN": "parent-secret",
            },
        ),
    }

    imported = restore_zellij_context(
        environment=environment,
        parent_pid=42,
        current_uid=1000,
        process_reader=contexts.get,
    )

    assert imported == {
        "ZELLIJ_SESSION_NAME": "current-session",
        "ZELLIJ_PANE_ID": "7",
        "XDG_RUNTIME_DIR": "/run/user/1000",
    }
    assert environment == {
        "ZELLIJ": "99",
        "ZELLIJ_SESSION_NAME": "current-session",
        "ZELLIJ_PANE_ID": "7",
        "XDG_RUNTIME_DIR": "/run/user/1000",
        "SECRET_TOKEN": "child-secret",
    }


def test_restore_uses_nearest_valid_same_uid_values_per_key():
    environment = {}
    calls = []
    contexts = {
        42: process_context(
            41,
            1000,
            {
                "ZELLIJ_SESSION_NAME": "nearest-session",
                "ZELLIJ_PANE_ID": "terminal_7",
                "XDG_RUNTIME_DIR": "relative/runtime",
            },
        ),
        41: process_context(
            1,
            1000,
            {
                "ZELLIJ": "0",
                "ZELLIJ_SESSION_NAME": "older-session",
                "ZELLIJ_PANE_ID": "8",
                "XDG_RUNTIME_DIR": "/run/user/1000",
            },
        ),
    }

    def read_process(pid):
        calls.append(pid)
        return contexts.get(pid)

    imported = restore_zellij_context(
        environment=environment,
        parent_pid=42,
        current_uid=1000,
        process_reader=read_process,
    )

    assert calls == [42, 41]
    assert imported == {
        "ZELLIJ": "0",
        "ZELLIJ_SESSION_NAME": "nearest-session",
        "ZELLIJ_PANE_ID": "8",
        "XDG_RUNTIME_DIR": "/run/user/1000",
    }


def test_restore_stops_at_different_uid_and_handles_cycles_or_reader_errors():
    environment = {}
    contexts = {
        42: process_context(41, 2000, {"ZELLIJ": "0"}),
        41: process_context(1, 1000, {"ZELLIJ": "1"}),
    }
    imported = restore_zellij_context(
        environment=environment,
        parent_pid=42,
        current_uid=1000,
        process_reader=contexts.get,
    )
    assert imported == {}
    assert environment == {}

    cyclic = {42: process_context(42, 1000, {"ZELLIJ": "0"})}
    assert restore_zellij_context(
        environment={},
        parent_pid=42,
        current_uid=1000,
        process_reader=cyclic.get,
    ) == {"ZELLIJ": "0"}

    def fail_reader(unused_pid):
        raise OSError("proc unavailable")

    assert restore_zellij_context(
        environment={},
        parent_pid=42,
        current_uid=1000,
        process_reader=fail_reader,
    ) == {}


def test_serve_restores_context_before_constructing_server(monkeypatch):
    events = []

    class FakeServer:
        def __init__(self):
            events.append("server")

        def serve_stdio(self):
            events.append("serve")

    monkeypatch.setattr(
        cli_module,
        "restore_zellij_context",
        lambda: events.append("restore"),
    )
    monkeypatch.setattr(cli_module, "ZellijMCPServer", FakeServer)

    assert cli_module.main(["serve"]) == 0
    assert events == ["restore", "server", "serve"]


def test_cli_requires_explicit_serve_command(capsys):
    assert cli_module.main([]) == 0
    assert "usage:" in capsys.readouterr().out


def test_real_process_reader_can_restore_current_parent_without_non_allowlist(monkeypatch):
    parent_environment = {
        "ZELLIJ": "0",
        "ZELLIJ_SESSION_NAME": "session",
        "ZELLIJ_PANE_ID": "3",
        "XDG_RUNTIME_DIR": "/run/user/{}".format(os.getuid()),
        "UNRELATED": "ignored",
    }
    environment = {}

    imported = restore_zellij_context(
        environment=environment,
        parent_pid=123,
        current_uid=os.getuid(),
        process_reader=lambda unused_pid: process_context(
            1,
            os.getuid(),
            parent_environment,
        ),
    )

    assert imported == {
        key: value
        for key, value in parent_environment.items()
        if key != "UNRELATED"
    }
    assert "UNRELATED" not in environment


def test_linux_process_reader_returns_only_allowlisted_environment():
    process = _read_linux_process(os.getpid())

    assert process is not None
    assert process["ppid"] == os.getppid()
    assert process["uid"] == os.getuid()
    assert set(process["environment"]) <= set(ZELLIJ_CONTEXT_KEYS)


def test_process_identity_parsers_handle_complex_names_and_reject_uid_changes():
    fields = ["S", "42"] + ["0"] * 17 + ["12345", "0"]
    stat = "123 (name with ) marker) {}\n".format(" ".join(fields)).encode("ascii")

    assert _parse_process_stat(stat) == (42, 12345)
    assert _parse_process_uid(b"Name:\ttest\nUid:\t1000\t1000\t1000\t1000\n") == 1000

    try:
        _parse_process_uid(b"Uid:\t1000\t0\t1000\t1000\n")
    except ValueError as exc:
        assert "differ" in str(exc)
    else:
        raise AssertionError("mismatched process uids must be rejected")
