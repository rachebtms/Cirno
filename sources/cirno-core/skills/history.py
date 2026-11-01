"""Inspect Skills and retain readable, content-addressed history in Home."""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from cirno.skills.metadata import parse_skill_metadata, valid_skill_metadata
from cirno.config.home import get_home_path
from filelock import FileLock


def validate_skill(directory: Path, *, document_content: str | None = None) -> dict:
    errors = []
    document = directory / "SKILL.md"
    if not document.is_file():
        return {"valid": False, "errors": ["SKILL.md is missing"]}
    metadata = parse_skill_metadata(
        document_content if document_content is not None else document.read_text(encoding="utf-8")
    )
    if metadata is None or not valid_skill_metadata(metadata, directory.name):
        errors.append(
            "SKILL.md needs matching name and a non-empty description in YAML frontmatter."
        )
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            errors.append(
                f"{path.relative_to(directory)} is a symbolic link; history requires regular files."
            )
        elif path.is_file() and path.suffix == ".py":
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (SyntaxError, UnicodeError) as exc:
                errors.append(str(exc))
        elif path.is_file() and path.suffix == ".sh":
            try:
                result = subprocess.run(
                    [
                        "bash"
                        if "bash" in path.read_text(encoding="utf-8").partition("\n")[0]
                        else "sh",
                        "-n",
                        str(path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
                errors.append(f"{path.relative_to(directory)}: syntax check failed: {exc}")
            else:
                if result.returncode:
                    errors.append(
                        result.stderr.strip()
                        or f"{path.relative_to(directory)}: syntax check exited with code {result.returncode}"
                    )
    return {"valid": not errors, "errors": errors}


def skill_directory(path: Path, home: Path | None = None) -> Path | None:
    root = ((home or get_home_path()) / "skills").resolve()
    try:
        relative = path.resolve().relative_to(root)
    except ValueError:
        return None
    return root / relative.parts[0] if relative.parts else None


def snapshot_skill(
    directory: Path, home: Path | None = None, *, document_content: str | None = None
) -> dict | None:
    if not directory.is_dir() or not (directory / "SKILL.md").exists():
        return None
    parent = (home or get_home_path()) / "skills-history" / directory.name
    parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(parent / ".lock")):
        with tempfile.TemporaryDirectory(dir=parent, prefix=".snapshot-") as temporary:
            staging = Path(temporary) / directory.name
            staging.mkdir()
            links = []
            for path in sorted(directory.rglob("*")):
                relative = path.relative_to(directory)
                if ".git" in relative.parts or "__pycache__" in relative.parts:
                    continue
                if path.is_symlink():
                    links.append(f"{relative} is a symbolic link; history requires regular files.")
                elif path.is_file():
                    target = staging / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if relative == Path("SKILL.md") and document_content is not None:
                        target.write_text(document_content, encoding="utf-8")
                    else:
                        shutil.copyfile(path, target)
            # Hash and validate the bytes being retained, not a second read of
            # the editable Skill, which may have changed while copying.
            digest = hashlib.sha256()
            for link in links:
                digest.update(b"symlink\0" + link.encode("utf-8"))
            files = sorted(path for path in staging.rglob("*") if path.is_file())
            for path in files:
                digest.update(str(path.relative_to(staging)).encode())
                digest.update(b"\0")
                with path.open("rb") as stream:
                    while chunk := stream.read(65536):
                        digest.update(chunk)
            revision = digest.hexdigest()
            destination = parent / revision
            if not destination.exists():
                validation = validate_skill(staging)
                validation["errors"].extend(links)
                validation["valid"] = not validation["errors"]
                (parent / (revision + ".json")).write_text(
                    json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                for path in files:
                    path.chmod(0o444)
                staging.replace(destination)
    return {
        "revision": revision,
        "path": str(destination),
        **json.loads((parent / (revision + ".json")).read_text(encoding="utf-8")),
    }


def inspect_skill(name: str, action: str, home: Path | None = None) -> dict:
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


def skill_versions(name: str, home: Path | None = None) -> list[dict]:
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
