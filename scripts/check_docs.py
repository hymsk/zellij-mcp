#!/usr/bin/env python3
"""Validate English-default documentation, translations, links, and boundaries."""

import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

LINK_PATTERN = re.compile(r"\[[^\]]*\]\((<[^>]+>|[^)]+)\)")
LANGUAGE_PATTERN = re.compile(r"(?:\.(cn|en|zh-cn))?\.md$")
PRIVATE_PATH_PATTERNS = (
    re.compile(r"/root/(?!\.local|\.config)"),
    re.compile(r"/home/[^/\s]+/"),
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+\\"),
)
EXCLUDED_MARKDOWN_DIRS = {
    ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "build", "dist",
    "__pycache__",
}
DOCUMENT_SECTIONS = (
    "architecture", "decisions", "design", "guides", "reference",
    "requirements", "testing",
)
LANGUAGES = ("cn", "en")


def current_markdown_files(root):
    """Return current docs while excluding the read-only history archive."""
    return sorted(
        path for path in root.rglob("*.md")
        if not EXCLUDED_MARKDOWN_DIRS.intersection(path.relative_to(root).parts)
        and root / "docs" / "history" not in path.parents
    )


def document_language(path):
    if path.name == "AGENTS.md":
        return None
    if path.name == "SPEC.md":
        return "cn"
    match = LANGUAGE_PATTERN.search(path.name)
    if not match or match.group(1) in {"en", "zh-cn"}:
        return None
    return match.group(1) or "en"


def edition_name(stem, language):
    return stem + (".cn.md" if language == "cn" else ".md")


def check_repository_symlinks(root):
    """Reject source-tree symlinks without following them or scanning artifacts."""
    errors = []
    for directory, directories, filenames in os.walk(str(root), followlinks=False):
        directories[:] = [name for name in directories if name not in EXCLUDED_MARKDOWN_DIRS]
        for name in directories + filenames:
            if name in EXCLUDED_MARKDOWN_DIRS:
                continue
            path = Path(directory) / name
            if path.is_symlink():
                errors.append("{} must not be a symlink".format(path.relative_to(root)))
    return errors


def prose_lines(content):
    """Yield numbered Markdown lines outside fenced code blocks."""
    fence = None
    for number, line in enumerate(content.splitlines(), 1):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence):
                fence = None
            continue
        if fence is None:
            yield number, line


def heading_anchors(content):
    """Collect GitHub-style anchors for the ATX headings used in this repo."""
    anchors = set()
    for _number, line in prose_lines(content):
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        title = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", match.group(1))
        slug = re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")
        anchor = slug
        suffix = 0
        while anchor in anchors:
            suffix += 1
            anchor = "{}-{}".format(slug, suffix)
        anchors.add(anchor)
    return anchors


def language_navigation(path):
    stem = LANGUAGE_PATTERN.sub("", path.name)
    return "[中文]({}.cn.md) | [English]({}.md)".format(stem, stem)


def is_language_navigation(path, number, line):
    navigation = language_navigation(path)
    return number in {3, 5, 7} and (
        line == navigation or line.startswith(navigation + " · ")
    )


def check_document_links(root, path, content):
    errors = []
    source = str(path.relative_to(root))
    language = document_language(path)
    for number, line in prose_lines(content):
        for raw_target in LINK_PATTERN.findall(line):
            target = raw_target.strip("<>")
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            target_path, unused_separator, fragment = target.partition("#")
            target_path, fragment = unquote(target_path), unquote(fragment)
            lexical_target = path.parent / target_path if target_path else path
            try:
                resolved = lexical_target.resolve()
            except (OSError, RuntimeError):
                errors.append("{} -> {} cannot resolve".format(source, raw_target))
                continue
            if not resolved.exists():
                errors.append("{} -> {} does not exist".format(source, raw_target))
                continue
            if language and lexical_target.suffix == ".md":
                target_language = document_language(lexical_target)
                switch = (
                    is_language_navigation(path, number, line)
                    and lexical_target.parent == path.parent
                    and LANGUAGE_PATTERN.sub("", lexical_target.name)
                    == LANGUAGE_PATTERN.sub("", path.name)
                )
                if lexical_target.is_symlink():
                    errors.append(
                        "{} -> {} uses a symlink".format(source, raw_target)
                    )
                elif (
                    target_language and target_language != language and not switch
                    and resolved != root / "SPEC.md"
                ):
                    errors.append(
                        "{} -> {} crosses document languages".format(source, raw_target)
                    )
                elif not target_language and lexical_target.name != "AGENTS.md":
                    errors.append(
                        "{} -> {} uses a noncanonical document name".format(source, raw_target)
                    )
            if (
                fragment and resolved.suffix == ".md" and resolved.is_file()
                and fragment not in heading_anchors(resolved.read_text(encoding="utf-8"))
            ):
                errors.append(
                    "{} -> {} has no matching heading anchor".format(source, raw_target)
                )
    return errors


def check_documentation(root):
    root = root.resolve()
    errors = check_repository_symlinks(root)
    files = current_markdown_files(root)
    readme = root / "README.md"
    if not readme.is_file() or readme.is_symlink():
        errors.append("README.md must be a regular English document")
    spec = root / "SPEC.md"
    if not spec.is_file() or spec.is_symlink():
        errors.append("SPEC.md must be a regular Chinese specification")
    for edition in ("SPEC.cn.md", "SPEC.en.md", "SPEC.zh-cn.md"):
        if (root / edition).exists() or (root / edition).is_symlink():
            errors.append("{} must not exist; maintain only SPEC.md in Chinese".format(edition))
    for path in files:
        if path.is_symlink():
            continue
        content = path.read_text(encoding="utf-8")
        source = str(path.relative_to(root))
        language = document_language(path)
        if language and path != spec:
            for other in LANGUAGES:
                sibling = path.with_name(edition_name(LANGUAGE_PATTERN.sub("", path.name), other))
                if not sibling.is_file() or sibling.is_symlink():
                    errors.append("{} has no real {} edition".format(source, other))
            lines = content.splitlines()
            if not any(
                is_language_navigation(path, number, line)
                for number, line in enumerate(lines, 1)
            ):
                errors.append("{} must have a language switch in its introduction".format(source))
        elif path.name != "AGENTS.md" and path != spec:
            errors.append("{} must use .md for English or .cn.md for Chinese".format(source))
        for pattern in PRIVATE_PATH_PATTERNS:
            match = pattern.search(content)
            if match:
                errors.append(
                    "{} references private absolute path {}".format(source, match.group(0))
                )
        errors.extend(check_document_links(root, path, content))

    for language in LANGUAGES:
        docs_index = root / "docs" / edition_name("README", language)
        if not docs_index.is_file():
            errors.append("{} is missing".format(docs_index.relative_to(root)))
            continue
        index_content = docs_index.read_text(encoding="utf-8")
        for section in DOCUMENT_SECTIONS:
            section_root = root / "docs" / section
            index_name = edition_name("README", language)
            section_index = section_root / index_name
            if not section_index.is_file():
                errors.append("docs/{}/{} is missing".format(section, index_name))
                continue
            if "({}/{})".format(section, index_name) not in index_content:
                errors.append(
                    "docs/{} does not link {}/{}".format(index_name, section, index_name)
                )
            content = section_index.read_text(encoding="utf-8")
            for child in sorted(section_root.glob("*.md")):
                if child == section_index or document_language(child) != language:
                    continue
                if "({})".format(child.name) not in content:
                    errors.append(
                        "docs/{}/{} does not index {}".format(section, index_name, child.name)
                    )
    return errors


def main():
    root = Path(__file__).resolve().parents[1]
    errors = check_documentation(root)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("checked English-default documents, translations, same-language links, "
          "heading anchors, and symlink-free source tree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
