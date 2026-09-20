"""Static quality constraints for the zellij-only Python 3.7 project."""

import ast
import re
import zipfile
from email.parser import Parser
from pathlib import Path

import pytest

from scripts.check_docs import edition_name

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = PROJECT_ROOT / "zellij_mcp"
CURRENT_DOC_SECTIONS = {
    "architecture",
    "decisions",
    "design",
    "guides",
    "reference",
    "requirements",
    "testing",
}
EXPECTED_TOOL_NAMES = (
    "zellij_mcp_doctor",
    "workspace_create",
    "workspace_list",
    "tab_list",
    "tab_focus",
    "tab_rename",
    "tab_close",
    "pane_write_text",
    "pane_send_key",
    "pane_screen",
    "pane_close",
)


def _call_strings(call):
    values = []
    for node in list(call.args) + [keyword.value for keyword in call.keywords]:
        for child in ast.walk(node):
            if isinstance(child, ast.Str):
                values.append(child.s)
    return values


def _call_name(call):
    function = call.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return ""


def test_runtime_process_calls_do_not_reference_other_multiplexers():
    forbidden = {"tmux", "screen"}
    violations = []
    for path in sorted(RUNTIME_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _call_name(node) not in {
                "Popen",
                "_cmd",
                "_run",
                "call",
                "check_call",
                "check_output",
                "run",
                "which",
            }:
                continue
            for value in _call_strings(node):
                words = set(value.lower().replace("/", " ").split())
                if words & forbidden:
                    violations.append("{}:{}:{}".format(
                        path.relative_to(PROJECT_ROOT),
                        node.lineno,
                        value,
                    ))

    assert violations == []


def test_package_metadata_keeps_python_37_floor():
    pyproject_text = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'requires-python = ">=3.7"' in pyproject_text
    assert 'license = "AGPL-3.0-or-later"' in pyproject_text
    assert 'email = "lxj_hymsk@163.com"' in pyproject_text


@pytest.mark.parametrize("language", ("cn", "en"))
def test_current_document_sections_have_indexes(language):
    missing = [
        section
        for section in sorted(CURRENT_DOC_SECTIONS)
        if not (PROJECT_ROOT / "docs" / section / edition_name("README", language)).is_file()
    ]

    assert missing == []


def test_tool_catalog_is_separate_from_server_handlers():
    from zellij_mcp.server.tool_catalog import build_tool_catalog
    from zellij_mcp.server.tool_runtime import ToolRuntime

    tools = build_tool_catalog()
    server_text = (RUNTIME_ROOT / "server" / "main.py").read_text(encoding="utf-8")

    assert tuple(tools) == EXPECTED_TOOL_NAMES
    assert tuple(ToolRuntime().handlers) == EXPECTED_TOOL_NAMES
    assert "def _configure_tool_schemas" not in server_text
    assert '"zellij_mcp_doctor": {' not in server_text
    assert "class MCPProtocol" not in server_text
    assert "class ToolRuntime" not in server_text


@pytest.mark.parametrize("language", ("cn", "en"))
def test_current_tool_documentation_lists_the_catalog_names(language):
    for filename in ("SPEC.md", edition_name("README", language)):
        content = (PROJECT_ROOT / filename).read_text(encoding="utf-8")
        names = tuple(re.findall(r"^\| `([^`]+)` \|", content, re.MULTILINE))
        assert names == EXPECTED_TOOL_NAMES, filename
    features = (
        PROJECT_ROOT / "docs" / "reference" / edition_name("features", language)
    ).read_text(encoding="utf-8")
    reference = (
        PROJECT_ROOT / "docs" / "reference" / edition_name("mcp-tools", language)
    ).read_text(encoding="utf-8")

    feature_block = re.search(r"```text\n(.*?)\n```", features, re.DOTALL)
    assert feature_block is not None
    feature_names = tuple(feature_block.group(1).splitlines())
    reference_names = tuple(
        name
        for unused_number, name in re.findall(
            r"^## ([0-9]+)\. ([a-z0-9_]+)$",
            reference,
            re.MULTILINE,
        )
    )

    assert feature_names == EXPECTED_TOOL_NAMES
    assert reference_names == EXPECTED_TOOL_NAMES


def test_tool_catalog_has_explicit_boolean_annotations():
    from zellij_mcp.server.tool_catalog import build_tool_catalog

    expected_fields = {
        "readOnlyHint",
        "destructiveHint",
        "idempotentHint",
        "openWorldHint",
    }
    for tool in build_tool_catalog().values():
        assert set(tool["annotations"]) == expected_fields
        assert all(type(value) is bool for value in tool["annotations"].values())


def test_workspace_list_description_explains_all_pane_counts():
    from zellij_mcp.server.tool_catalog import build_tool_catalog

    description = build_tool_catalog()["workspace_list"]["description"]

    assert "total_pane_count" in description
    assert "terminal_pane_count" in description
    assert "plugin_pane_count" in description
    assert "pane_count" in description


def test_catalog_describes_every_parameter_and_advertises_actual_defaults():
    from zellij_mcp.server.tool_catalog import build_tool_catalog

    expected_defaults = {
        "workspace_create": {"workspace_type": "auto", "focus": False},
        "workspace_list": {"all_sessions": False, "include_plugins": False},
        "tab_list": {"all_sessions": False, "include_panes": True},
        "tab_close": {"force": False},
        "pane_screen": {"full": False, "ansi": False},
        "pane_close": {"force": False},
    }
    for name, tool in build_tool_catalog().items():
        properties = tool["inputSchema"]["properties"]
        for parameter, schema in properties.items():
            assert schema.get("description", "").strip(), (name, parameter)
            if schema["type"] == "boolean":
                assert type(schema.get("default")) is bool, (name, parameter)
        assert {
            key: schema["default"] for key, schema in properties.items()
            if "default" in schema
        } == expected_defaults.get(name, {})


def test_tool_descriptions_keep_critical_guidance_without_initialize():
    from zellij_mcp.server.tool_catalog import build_tool_catalog

    tools = build_tool_catalog()
    assert "persistent interactive or background terminal tasks" in (
        tools["workspace_create"]["description"]
    )
    assert len(tools["workspace_create"]["description"]) <= 420
    for name in ("workspace_create", "tab_focus"):
        assert "user requests" in tools[name]["description"]
        assert "attention" in tools[name]["description"]
    create = tools["workspace_create"]["description"]
    assert "confirmed exited or completed" in create
    assert "unless the user requested retention" in create
    for name in ("pane_close", "tab_close"):
        description = tools[name]["description"]
        assert "Promptly" in description
        assert "verified finished tasks" in description
        assert "never unrelated/running/retained work" in description
        assert "Save results; refresh" in description
        assert "Protects MCP" in description
        force = tools[name]["inputSchema"]["properties"]["force"]["description"]
        assert "Must be true to close" in force
    assert "tab_list(include_panes=true)" in tools["tab_close"]["description"]
    assert "pane_close for one pane" in tools["tab_close"]["description"]
    for name in ("pane_screen", "pane_write_text", "pane_send_key"):
        assert "without changing focus" in tools[name]["description"]
        assert "completion" in tools[name]["description"]
    for name in ("pane_write_text", "pane_send_key"):
        assert "inspected pane" in tools[name]["description"]
    assert "embedded newlines may submit" in tools["pane_write_text"]["description"]
    assert "Ctrl-C/Ctrl-D may interrupt/exit" in tools["pane_send_key"]["description"]
    assert "snapshot or silence alone" in tools["pane_screen"]["description"]
    assert "262144" in tools["pane_screen"]["description"]
    assert "Never needed for discovery/read/write" in tools["tab_focus"]["description"]


def test_catalog_description_budget_and_creation_caveats():
    from zellij_mcp.server.tool_catalog import build_tool_catalog

    tools = build_tool_catalog()
    descriptions = [tool["description"] for tool in tools.values()]
    descriptions.extend(
        parameter["description"]
        for tool in tools.values()
        for parameter in tool["inputSchema"]["properties"].values()
    )
    assert sum(map(len, descriptions)) <= 5200
    properties = tools["workspace_create"]["inputSchema"]["properties"]
    for guidance in ("identical", "not across restarts", "unknown outcomes", "discover"):
        assert guidance in properties["request_id"]["description"]
    assert "explicit shell" in properties["command"]["description"]
    assert "not necessarily the Host project" in properties["cwd"]["description"]
    assert "rejecting existing names" in properties["workspace_type"]["description"]
    assert "normally omit" in properties["return_tab_id"]["description"]
    assert "incompatible with return_tab_id" in properties["focus"]["description"]


def test_makefile_exposes_stable_quality_and_integration_targets():
    makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")

    for target in (
        "verify:",
        "integration-smoke:",
        "integration-installed:",
        "integration-isolated:",
        "integration-tab:",
        "integration-pane:",
    ):
        assert target in makefile


def test_project_has_no_placeholder_utils_or_unmanaged_host_example():
    assert not (RUNTIME_ROOT / "utils").exists()


@pytest.mark.parametrize("language", ("cn", "en"))
def test_spec_requirement_ids_match_traceability_matrix(language):
    pattern = re.compile(r"^\| (ZMCP-[A-Z]+-[0-9]{3}) \|", re.MULTILINE)
    requirement_text = (
        PROJECT_ROOT / "SPEC.md"
    ).read_text(encoding="utf-8")
    coverage_text = (
        PROJECT_ROOT / "docs" / "testing" / edition_name("requirements-coverage", language)
    ).read_text(encoding="utf-8")

    requirement_ids = pattern.findall(requirement_text)
    coverage_ids = pattern.findall(coverage_text)

    assert len(requirement_ids) == len(set(requirement_ids))
    assert len(coverage_ids) == len(set(coverage_ids))
    assert {item for item in requirement_ids if item.startswith("ZMCP-MVP-")} == {
        "ZMCP-MVP-{:03d}".format(number) for number in range(1, 25)
    }
    assert set(requirement_ids) == set(coverage_ids)


def test_spec_is_a_single_chinese_document():
    from scripts.check_docs import document_language

    spec = PROJECT_ROOT / "SPEC.md"
    assert spec.is_file() and not spec.is_symlink()
    assert document_language(spec) == "cn"
    assert "仅维护中文版本" in spec.read_text(encoding="utf-8")
    assert sorted(path.name for path in PROJECT_ROOT.glob("SPEC*.md")) == ["SPEC.md"]


@pytest.mark.parametrize("language", ("cn", "en"))
def test_both_languages_link_the_single_spec_without_relaxing_other_links(tmp_path, language):
    from scripts.check_docs import check_document_links

    source = tmp_path / edition_name("README", language)
    source.write_text("# Project\n", encoding="utf-8")
    (tmp_path / "SPEC.md").write_text("# 规范\n", encoding="utf-8")
    assert check_document_links(tmp_path, source, "[SPEC](SPEC.md#规范)") == []
    errors = check_document_links(tmp_path, source, "[SPEC](SPEC.md#missing)")
    assert any("has no matching heading anchor" in error for error in errors)
    other = "en" if language == "cn" else "cn"
    guide = edition_name("guide", other)
    (tmp_path / guide).write_text("# Guide\n", encoding="utf-8")
    errors = check_document_links(tmp_path, source, "[Guide]({})".format(guide))
    assert any("crosses document languages" in error for error in errors)


@pytest.mark.parametrize("edition", ("SPEC.cn.md", "SPEC.en.md", "SPEC.zh-cn.md"))
def test_documentation_rejects_duplicate_spec_editions(tmp_path, edition):
    from scripts.check_docs import check_documentation

    (tmp_path / "SPEC.md").write_text("# 规范\n", encoding="utf-8")
    (tmp_path / edition).write_text("# Duplicate\n", encoding="utf-8")
    assert (
        "{} must not exist; maintain only SPEC.md in Chinese".format(edition)
        in check_documentation(tmp_path)
    )


def test_english_default_documentation_links_and_regular_files():
    from scripts.check_docs import check_documentation

    assert check_documentation(PROJECT_ROOT) == []


def test_document_link_checks_reject_language_drift_and_stale_anchors(tmp_path):
    from scripts.check_docs import check_document_links

    source = tmp_path / "README.cn.md"
    source.write_text("# 项目\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
    (tmp_path / "guide.cn.md").write_text("# 安装\n", encoding="utf-8")
    (tmp_path / "guide.md").write_text("# Install\n", encoding="utf-8")
    valid = (
        "# 项目\n\n[中文](README.cn.md) | [English](README.md)\n\n"
        "[安装](guide.cn.md#安装)\n"
    )
    assert check_document_links(tmp_path, source, valid) == []
    for target, expected in (
        ("guide.md#install", "crosses document languages"),
        ("guide.cn.md#install", "has no matching heading anchor"),
        ("missing.cn.md", "does not exist"),
        ("README.md", "crosses document languages"),
    ):
        errors = check_document_links(tmp_path, source, valid + "\n[链接]({})\n".format(target))
        assert any(expected in error for error in errors), (target, errors)


def test_english_document_links_use_default_paths_and_same_page_switch(tmp_path):
    from scripts.check_docs import check_document_links

    source = tmp_path / "README.md"
    valid = (
        "# Project\n\n[中文](README.cn.md) | [English](README.md)\n\n"
        "[Install](guide.md#install)\n"
    )
    source.write_text(valid, encoding="utf-8")
    (tmp_path / "README.cn.md").write_text("# 项目\n", encoding="utf-8")
    (tmp_path / "guide.md").write_text("# Install\n", encoding="utf-8")
    (tmp_path / "guide.cn.md").write_text("# 安装\n", encoding="utf-8")
    assert check_document_links(tmp_path, source, valid) == []
    errors = check_document_links(tmp_path, source, valid + "\n[安装](guide.cn.md#安装)\n")
    assert any("crosses document languages" in error for error in errors)


@pytest.mark.parametrize("intro, navigation_line", (
    ("# Project\n\n", 3),
    ("# Project\n\n> Summary.\n\n", 5),
    ("# Project\n\n> Summary.\n\nIntroduction.\n\n", 7),
))
def test_readme_intro_navigation_allows_only_same_page_language_switch(
    tmp_path, intro, navigation_line,
):
    from scripts.check_docs import check_document_links, is_language_navigation

    source = tmp_path / "README.md"
    navigation = "[中文](README.cn.md) | [English](README.md) · [Guide](guide.md)"
    content = intro + navigation + "\n"
    source.write_text(content, encoding="utf-8")
    (tmp_path / "README.cn.md").write_text("# 项目\n", encoding="utf-8")
    (tmp_path / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (tmp_path / "guide.cn.md").write_text("# 指南\n", encoding="utf-8")
    assert is_language_navigation(source, navigation_line, navigation)
    assert not is_language_navigation(source, 20, navigation)
    assert check_document_links(tmp_path, source, content) == []
    errors = check_document_links(
        tmp_path, source, content.replace("[Guide](guide.md)", "[指南](guide.cn.md)"),
    )
    assert any("crosses document languages" in error for error in errors)


@pytest.mark.parametrize("name", ("README.en.md", "README.zh-cn.md"))
def test_documentation_rejects_legacy_language_aliases(tmp_path, name):
    from scripts.check_docs import check_documentation

    (tmp_path / name).write_text("# Legacy\n", encoding="utf-8")
    errors = check_documentation(tmp_path)
    assert "{} must use .md for English or .cn.md for Chinese".format(name) in errors


@pytest.mark.parametrize("name", ("README.md", "README.cn.md"))
def test_documentation_requires_regular_translation_pairs(tmp_path, name):
    from scripts.check_docs import check_documentation, language_navigation

    path = tmp_path / name
    path.write_text("# Project\n\n" + language_navigation(path) + "\n", encoding="utf-8")
    missing_language = "cn" if name == "README.md" else "en"
    errors = check_documentation(tmp_path)
    assert "{} has no real {} edition".format(name, missing_language) in errors


def test_source_tree_check_rejects_file_and_directory_symlinks(tmp_path, monkeypatch):
    from scripts.check_docs import check_repository_symlinks

    (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / ".venv").mkdir()
    assert check_repository_symlinks(tmp_path) == []
    # Model symlink metadata without creating any symlinks in the test environment.
    monkeypatch.setattr(
        Path, "is_symlink", lambda path: path.name in {"README.md", "docs", ".venv"},
    )
    assert sorted(check_repository_symlinks(tmp_path)) == [
        "README.md must not be a symlink", "docs must not be a symlink",
    ]


def test_documentation_rejects_symlink_readme_and_links(tmp_path, monkeypatch):
    from scripts.check_docs import check_document_links, check_documentation

    readme = tmp_path / "README.md"
    readme.write_text("# Project\n", encoding="utf-8")
    source = tmp_path / "guide.md"
    source.write_text("# Guide\n", encoding="utf-8")
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == readme)
    assert "README.md must be a regular English document" in check_documentation(tmp_path)
    assert any(
        "uses a symlink" in error
        for error in check_document_links(tmp_path, source, "[Project](README.md)")
    )


def test_current_docs_use_public_tool_names():
    stale = []
    roots = [PROJECT_ROOT / "docs", PROJECT_ROOT / "scripts"]
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.suffix not in {".md", ".py"}:
                continue
            if "workspace_close" in path.read_text(encoding="utf-8"):
                stale.append(str(path.relative_to(PROJECT_ROOT)))

    assert stale == []


def test_makefile_exposes_reproducible_sdd_quality_gate():
    makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")

    for target in (
        "dev-install:",
        "security:",
        "audit:",
    ):
        assert target in makefile
    assert "audit: verify test-cov typecheck security" in makefile


def test_python37_development_dependencies_are_bounded():
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    for dependency in (
        "pytest>=7.0,<8.0",
        "pytest-cov>=4.0,<5.0",
        "coverage>=7.0,<7.3",
        "mypy>=1.0,<1.5",
        "bandit>=1.7.5,<1.8",
    ):
        assert '"{}"'.format(dependency) in pyproject
    assert '"ruff>=0.16,<0.17"' in pyproject


def test_build_backend_exports_development_extra_metadata():
    from zellij_mcp import build_backend

    metadata = build_backend._metadata(
        "1.0.0rc1",
        ("a" * 40, False),
    ).decode("utf-8")

    assert "Provides-Extra: dev\n" in metadata
    assert "License-Expression: AGPL-3.0-or-later\n" in metadata
    assert "License-File: LICENSE\n" in metadata
    assert "Author-email: lxj_hymsk@163.com\n" in metadata
    assert "X-Zellij-MCP-Source-Commit: {}\n".format("a" * 40) in metadata
    assert "X-Zellij-MCP-Source-Dirty: false\n" in metadata
    for dependency in (
        "pytest (>=7.0,<8.0)",
        "pytest-cov (>=4.0,<5.0)",
        "coverage (>=7.0,<7.3)",
        "mypy (>=1.0,<1.5)",
        "ruff (>=0.16,<0.17)",
        "bandit (>=1.7.5,<1.8)",
    ):
        assert 'Requires-Dist: {} ; extra == "dev"\n'.format(dependency) in metadata
    parsed = Parser().parsestr(metadata)
    assert parsed["Description-Content-Type"] == "text/markdown"
    assert parsed.get_payload() == (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert 'readme = "{}"'.format(build_backend.README_FILENAME) in (
        PROJECT_ROOT / "pyproject.toml"
    ).read_text(encoding="utf-8")


@pytest.mark.parametrize("declaration, expected", (
    ('__version__ = "1.0.0rc1"', "1.0.0rc1"),
    ("__version__ = '0.2.0'", "0.2.0"),
    ('__version__ = "1.0." "0rc1"', "1.0.0rc1"),
))
def test_build_backend_reads_literal_version_without_executing_module(
    tmp_path, monkeypatch, declaration, expected,
):
    from zellij_mcp import build_backend

    package = tmp_path / "zellij_mcp"
    package.mkdir()
    (package / "__init__.py").write_text(
        'raise RuntimeError("package must not execute during build")\n' + declaration + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(build_backend, "_root", lambda: str(tmp_path))

    assert build_backend._version() == expected


@pytest.mark.parametrize("declaration", (
    "__version__ = 123",
    '__version__ = b"0.1.0"',
    '__version__ = str("0.1.0")',
    'different_name = "0.1.0"',
))
def test_build_backend_rejects_nonliteral_or_missing_string_version(
    tmp_path, monkeypatch, declaration,
):
    from zellij_mcp import build_backend

    package = tmp_path / "zellij_mcp"
    package.mkdir()
    (package / "__init__.py").write_text(declaration + "\n", encoding="utf-8")
    monkeypatch.setattr(build_backend, "_root", lambda: str(tmp_path))

    with pytest.raises(RuntimeError, match="version declaration is missing or invalid"):
        build_backend._version()


def test_build_metadata_reads_default_english_readme_not_translation(tmp_path, monkeypatch):
    from zellij_mcp import build_backend

    readme = "# Package\n\n[中文](README.cn.md) | [English](README.md)\n"
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    (tmp_path / "README.cn.md").write_text("# 中文翻译\n", encoding="utf-8")
    monkeypatch.setattr(build_backend, "_root", lambda: str(tmp_path))

    metadata = Parser().parsestr(build_backend._metadata("1.0.0rc1", ("a" * 40, False)).decode())

    assert metadata["Description-Content-Type"] == "text/markdown"
    assert metadata.get_payload() == readme


def test_build_backend_builds_regular_and_editable_wheels(tmp_path, monkeypatch):
    from zellij_mcp import build_backend

    monkeypatch.setenv("ZELLIJ_MCP_SOURCE_COMMIT", "b" * 40)
    monkeypatch.setenv("ZELLIJ_MCP_SOURCE_DIRTY", "false")
    regular_directory = tmp_path / "regular"
    editable_directory = tmp_path / "editable"
    regular_name = build_backend.build_wheel(str(regular_directory))
    editable_name = build_backend.build_editable(str(editable_directory))

    with zipfile.ZipFile(str(regular_directory / regular_name)) as archive:
        regular_files = set(archive.namelist())
        build_info = archive.read("zellij_mcp/_build_info.py").decode("utf-8")
        metadata = archive.read(
            "zellij_mcp-1.0.0rc1.dist-info/METADATA"
        ).decode("utf-8")
    with zipfile.ZipFile(str(editable_directory / editable_name)) as archive:
        editable_files = set(archive.namelist())
        editable_metadata = archive.read(
            "zellij_mcp-1.0.0rc1.dist-info/METADATA"
        ).decode("utf-8")

    assert "zellij_mcp/cli.py" in regular_files
    assert "SOURCE_COMMIT = {!r}".format("b" * 40) in build_info
    assert "SOURCE_DIRTY = False" in build_info
    assert "X-Zellij-MCP-Source-Commit: {}".format("b" * 40) in metadata
    assert any(path.endswith("/licenses/LICENSE") for path in regular_files)
    assert "zellij_mcp.pth" not in regular_files
    assert "zellij_mcp.pth" in editable_files
    assert "zellij_mcp/cli.py" not in editable_files
    assert editable_metadata == metadata
    parsed = Parser().parsestr(metadata)
    assert parsed["Description-Content-Type"] == "text/markdown"
    assert parsed.get_payload() == (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")


def test_build_backend_prepares_metadata_and_rejects_sdists(tmp_path):
    from zellij_mcp import build_backend

    info_name = build_backend.prepare_metadata_for_build_editable(str(tmp_path))
    metadata = (tmp_path / info_name / "METADATA").read_text(encoding="utf-8")

    assert "Provides-Extra: dev" in metadata
    prepared = Parser().parsestr(metadata)
    assert prepared["Description-Content-Type"] == "text/markdown"
    assert prepared.get_payload() == (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    with pytest.raises(RuntimeError, match="source distributions are not supported"):
        build_backend.build_sdist(str(tmp_path))


def test_build_backend_rejects_invalid_configured_commit(monkeypatch):
    from zellij_mcp import build_backend

    monkeypatch.setenv("ZELLIJ_MCP_SOURCE_COMMIT", "not-a-commit")
    with pytest.raises(RuntimeError, match="full commit hash"):
        build_backend._source_provenance()
