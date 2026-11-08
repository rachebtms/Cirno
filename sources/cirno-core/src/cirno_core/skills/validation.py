"""Validate a Skill's runtime contract, file types and retained scripts."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import TypedDict

from cirno_core.skills.metadata import parse_skill_metadata, valid_skill_metadata
from cirno_core.skills.runtime_metadata import SkillMetadataError, parse_runtime_metadata
from cirno_core.utils.directory_tree import TreeEntry, walk_tree

SKILL_TREE_IGNORES = frozenset({".git", "__pycache__"})


class SkillValidation(TypedDict):
    valid: bool
    errors: list[str]


def unsupported_entry(entry: TreeEntry, root: Path) -> str | None:
    relative = entry.path.relative_to(root).as_posix()
    if entry.is_symlink:
        return f"{relative} is a symbolic link or reparse point; history requires regular files."
    if not entry.is_file and not entry.is_dir:
        return f"{relative} is not a regular file or directory; history cannot retain it."
    return None


def validate_skill(directory: Path, *, document_content: str | None = None) -> SkillValidation:
    try:
        directory.lstat()
    except (FileNotFoundError, NotADirectoryError):
        return {"valid": False, "errors": ["SKILL.md is missing"]}
    entries = list(walk_tree(directory, skip_names=SKILL_TREE_IGNORES))
    errors = [message for entry in entries if (message := unsupported_entry(entry, directory))]
    document = directory / "SKILL.md"
    if not any(entry.path == document and entry.is_file for entry in entries):
        return {"valid": False, "errors": ["SKILL.md is missing", *errors]}
    metadata = parse_skill_metadata(
        document_content if document_content is not None else document.read_text(encoding="utf-8")
    )
    if metadata is None or not valid_skill_metadata(metadata, directory.name):
        errors.append(
            "SKILL.md needs matching name and a non-empty description in YAML frontmatter."
        )
    else:
        try:
            parse_runtime_metadata(metadata)
        except SkillMetadataError as error:
            errors.append(str(error))
    for entry in entries:
        path = entry.path
        if not entry.is_file:
            continue
        if path.suffix == ".py":
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (SyntaxError, UnicodeError) as error:
                errors.append(str(error))
        elif path.suffix == ".sh":
            try:
                shell = (
                    "bash"
                    if "bash" in path.read_text(encoding="utf-8").partition("\n")[0]
                    else "sh"
                )
                result = subprocess.run(
                    [shell, "-n", str(path)], capture_output=True, text=True, timeout=5
                )
            except (OSError, UnicodeError, subprocess.TimeoutExpired) as error:
                errors.append(f"{path.relative_to(directory)}: syntax check failed: {error}")
            else:
                if result.returncode:
                    errors.append(
                        result.stderr.strip()
                        or f"{path.relative_to(directory)}: syntax check exited with code {result.returncode}"
                    )
    return {"valid": not errors, "errors": errors}
