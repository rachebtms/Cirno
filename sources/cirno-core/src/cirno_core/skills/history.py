"""Inspect Skills and retain readable, content-addressed history in Home."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any

from cirno_core.config.home import get_home_path
from cirno_core.skills.validation import SKILL_TREE_IGNORES, unsupported_entry, validate_skill
from cirno_core.utils.atomic_file import atomic_write_text
from cirno_core.utils.directory_tree import walk_tree
from filelock import FileLock


def skill_directory(path: Path, home: Path | None = None) -> Path | None:
    root = ((home or get_home_path()) / "skills").resolve()
    try:
        relative = path.resolve().relative_to(root)
    except ValueError:
        return None
    return root / relative.parts[0] if relative.parts else None


def snapshot_skill(
    directory: Path, home: Path | None = None, *, document_content: str | None = None
) -> dict[str, Any] | None:
    try:
        mode = directory.lstat().st_mode
    except (FileNotFoundError, NotADirectoryError):
        return None
    if not stat.S_ISDIR(mode) and not stat.S_ISLNK(mode):
        return None
    parent = (home or get_home_path()) / "skills-history" / directory.name
    parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(parent / ".lock")):
        with tempfile.TemporaryDirectory(dir=parent, prefix=".snapshot-") as temporary:
            staging = Path(temporary) / directory.name
            staging.mkdir()
            rejected: list[str] = []
            for entry in walk_tree(directory, skip_names=SKILL_TREE_IGNORES):
                path = entry.path
                relative = path.relative_to(directory)
                if message := unsupported_entry(entry, directory):
                    rejected.append(message)
                elif entry.is_dir:
                    (staging / relative).mkdir(parents=True, exist_ok=True)
                elif entry.is_file:
                    target = staging / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if relative == Path("SKILL.md") and document_content is not None:
                        target.write_text(document_content, encoding="utf-8")
                    else:
                        shutil.copyfile(path, target)
            # Hash and validate the bytes being retained, not a second read of
            # the editable Skill, which may have changed while copying.
            digest = hashlib.sha256(b"cirno-skill-tree-v2\0")
            digest.update(json.dumps(rejected, ensure_ascii=False).encode("utf-8") + b"\0")
            files: list[Path] = []
            for entry in walk_tree(staging):
                path = entry.path
                relative = path.relative_to(staging).as_posix().encode("utf-8")
                digest.update(
                    (b"dir\0" if entry.is_dir else b"file\0")
                    + len(relative).to_bytes(8, "big")
                    + relative
                )
                if entry.is_dir:
                    continue
                files.append(path)
                content_digest = hashlib.sha256()
                with path.open("rb") as stream:
                    while chunk := stream.read(65536):
                        content_digest.update(chunk)
                digest.update(content_digest.digest())
            revision = digest.hexdigest()
            destination = parent / revision
            if not destination.exists():
                validation = validate_skill(staging)
                validation["errors"].extend(rejected)
                validation["valid"] = not validation["errors"]
                metadata_path = parent / (revision + ".json")
                try:
                    atomic_write_text(
                        metadata_path, json.dumps(validation, ensure_ascii=False, indent=2)
                    )
                    for path in files:
                        path.chmod(0o444)
                    staging.replace(destination)
                except BaseException:
                    metadata_path.unlink(missing_ok=True)
                    raise
    return {
        "revision": revision,
        "path": str(destination),
        **json.loads((parent / (revision + ".json")).read_text(encoding="utf-8")),
    }


def inspect_skill(name: str, action: str, home: Path | None = None) -> dict[str, Any]:
    """Shared settings/tool operation; reading history never creates a version."""
    if "/" in name or "\\" in name or name in {"", ".", ".."}:
        raise ValueError("Invalid skill name")
    if action == "history":
        return {"versions": skill_versions(name, home)}
    if action != "validate":
        raise ValueError("Unknown skill action")
    directory = (home or get_home_path()) / "skills" / name
    version = snapshot_skill(directory, home)
    validation = (
        {key: version[key] for key in ("valid", "errors")} if version else validate_skill(directory)
    )
    return {"version": version, "validation": validation, "versions": skill_versions(name, home)}


def capture_skill_path(path: Path) -> None:
    directory = skill_directory(path)
    if directory is not None:
        snapshot_skill(directory)


def skill_versions(name: str, home: Path | None = None) -> list[dict[str, Any]]:
    if "/" in name or "\\" in name or name in {"", ".", ".."}:
        raise ValueError("Invalid skill name")
    root = (home or get_home_path()) / "skills-history" / name
    if not root.exists():
        return []
    return [
        {
            "revision": path.name,
            "path": str(path),
            "validation": json.loads((root / (path.name + ".json")).read_text()),
        }
        for path in sorted(root.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)
        if path.is_dir() and not path.name.startswith(".")
    ]
