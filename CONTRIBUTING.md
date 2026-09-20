# Contributing

[中文](CONTRIBUTING.cn.md) | [English](CONTRIBUTING.md)

## Development

Read [SPEC.md](SPEC.md) before making changes. This single Chinese-only specification defines requirements, public behavior, and acceptance criteria. Update it and the coverage matrix when behavior changes, then align the implementation and references. Maintain equivalent Chinese and English editions of other human-facing documents: English uses plain `*.md` files and Chinese uses `*.cn.md`. All documents are regular files, not symlinks or duplicate aliases. Body links stay in the selected language except for shared references to `SPEC.md`.

For a new environment, first [install zellij](docs/guides/installation.md#install-zellij) and configure `PATH`, then install development dependencies. Before running real zellij integration tests, run `python3 -m zellij_mcp doctor --json` to check capabilities.

```bash
python3 -m pip install -e ".[dev]"
make check
make verify
python3 tests/integration/server_smoke.py
python3 tests/integration/installed_wheel_smoke.py
python3 tests/integration/zellij_isolated_lifecycle.py
```

This project has no GitHub Actions CI. Run relevant checks locally. Real lifecycle tests create and close sessions, Tabs, and panes and must be invoked explicitly. See the [testing documentation](docs/testing/README.md) for commands and side effects.

## Commits

Use Conventional Commits: `<type>[(scope)][!]: <summary>`. Common types include `feat`, `fix`, `refactor`, `docs`, `test`, `build`, `ci`, and `chore`. Keep each commit focused on one logical purpose; use a concise, meaningful title rather than a version number or a vague update description.

- Initial public commits, initial imports, and squashed public baselines must include a substantive body. Release commits, public behavior or compatibility changes, complex fixes, and large refactors must explain the context and impact that the title cannot convey. Small, straightforward corrections need no boilerplate.
- Explain the purpose, main capabilities or changes, relevant modules, compatibility and safety boundaries, and key trade-offs. A file list or `initial release` is not an adequate explanation. Mark breaking changes with `!` and describe migration requirements.
- Record relevant checks actually performed and their results, including checks not run, failures, and environment limitations. Test files are not proof that tests passed; do not invent verification claims or review trailers.
- Before committing, review the full diff and complete message. After committing, inspect `git log -1 --format=full` to confirm the body was saved. Older terse commits do not waive these requirements; squashing does not remove the need for a meaningful body.
- AI contributors must not stage, commit, or push without explicit authorization for the corresponding operation. Commit authorization does not include pushing or publishing a Release; push authorization covers existing commits only, not uncommitted changes.

Message structure (replace placeholders with verified facts and remove inapplicable items):

```text
<type>[(scope)][!]: <summary>

<Purpose, context, and key trade-offs>

- <Main capability or behavior change>
- <Compatibility, safety boundary, or migration impact>

Validation: <Actual commands and results; unverified items and reasons>
```

## Releases

- A commit body explains a logical change, a tag identifies a version, and GitHub Release notes explain that version to users. They are separate deliverables, not substitutes; a tag alone is not a GitHub Release.
- Before publishing, verify the tag, target commit, package version, and prerelease flag. `v1.0.0rc1` is the public compatibility baseline; evaluate subsequent public MCP tool, CLI, and configuration changes against it. Release candidates must be marked as prereleases.
- Every new public GitHub Release must have substantive notes. The first release describes the available capabilities and boundaries; later releases describe changes since the preceding version. A version number, commit-title list, or automatically generated comparison link alone is insufficient.
- Provide equivalent English and Chinese release notes covering: release status, main capabilities or changes, installation or upgrade links, compatibility and migration requirements, known limitations, and verification supported by evidence. Explicitly identify checks not run or not passed; do not claim GitHub Actions CI passed, since this project has none.
- Verify links and describe only content present at the tagged commit, not uncommitted or later changes. State applicable Python and zellij requirements and relevant session, Tab, and pane side effects without claiming support beyond the documented and verified scope.
- Prepare and review notes before obtaining explicit authorization to create or edit an online Release. Missing notes for an existing tag can be added without changing its commit; this does not repair the original commit body. Rewriting published history, moving an existing tag, or force-pushing requires separate explicit authorization and is not an implicit part of documentation repair.

## Pull requests

- When changing MCP tools, parameters, or return structures, update the specification, both documentation languages, interface references, requirement coverage, and tests.
- When changing zellij action contracts, update the architecture, ADRs, and real integration probes.
- Preserve Python 3.7 compatibility and avoid syntax available only in newer versions.
- Do not commit credentials, user Host configuration, test caches, build artifacts, or developer-specific absolute paths.
