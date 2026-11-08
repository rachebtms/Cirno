"""Bounded CLI output and created-artifact reporting."""

from __future__ import annotations

from pathlib import Path

_MAX_TOOL_OUTPUT_CHARS = 12_000


_MAX_ARTIFACT_SCAN_PATHS = 4_000


_MAX_ARTIFACT_REPORT = 12


_ARTIFACT_EXTENSIONS = frozenset(
    {
        ".csv",
        ".drawio",
        ".gif",
        ".html",
        ".jpeg",
        ".jpg",
        ".json",
        ".md",
        ".pdf",
        ".png",
        ".svg",
        ".txt",
        ".vsdx",
        ".webp",
        ".xml",
    }
)


_INLINE_ARTIFACT_EXTENSIONS = frozenset({".gif", ".jpeg", ".jpg", ".png", ".webp"})


_ARTIFACT_IGNORE_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".cirno",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)


def _truncate(text: str, limit: int = _MAX_TOOL_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return text[:limit] + f"\n\n... truncated {omitted} characters ..."


def _iter_artifact_candidates(cwd: Path) -> list[Path]:
    if not cwd.is_dir():
        return []
    out: list[Path] = []
    stack = [cwd]
    scanned = 0
    while stack and scanned < _MAX_ARTIFACT_SCAN_PATHS:
        directory = stack.pop()
        try:
            entries = sorted(directory.iterdir(), key=lambda path: path.name.lower())
        except OSError:
            continue
        for path in entries:
            if scanned >= _MAX_ARTIFACT_SCAN_PATHS:
                break
            scanned += 1
            try:
                if path.is_dir() and not path.is_symlink():
                    if path.name not in _ARTIFACT_IGNORE_DIRS:
                        stack.append(path)
                    continue
                if path.is_file() and path.suffix.lower() in _ARTIFACT_EXTENSIONS:
                    out.append(path.resolve(strict=False))
            except OSError:
                continue
    return out


def _artifact_snapshot(cwd: Path) -> dict[Path, tuple[int, int]]:
    snapshot: dict[Path, tuple[int, int]] = {}
    for path in _iter_artifact_candidates(cwd):
        try:
            stat = path.stat()
        except OSError:
            continue
        snapshot[path] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def _changed_artifacts(
    cwd: Path,
    before: dict[Path, tuple[int, int]],
) -> list[Path]:
    changed: list[tuple[int, Path]] = []
    for path, stamp in _artifact_snapshot(cwd).items():
        if before.get(path) == stamp:
            continue
        changed.append((stamp[0], path))
    changed.sort(key=lambda item: (item[0], item[1].name.lower()))
    return [path for _, path in changed[-_MAX_ARTIFACT_REPORT:]]


def _format_artifact_path(cwd: Path, path: Path) -> str:
    try:
        return path.relative_to(cwd).as_posix()
    except ValueError:
        return path.name


def _format_artifact_size(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return "unknown size"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _format_artifact_lines(cwd: Path, paths: list[Path]) -> list[str]:
    lines: list[str] = []
    for path in paths:
        rel = _format_artifact_path(cwd, path)
        ext = path.suffix.lower()
        kind = (
            "previewable image" if ext in _INLINE_ARTIFACT_EXTENSIONS else ext.lstrip(".") or "file"
        )
        lines.append(f"- {rel} ({kind}, {_format_artifact_size(path)})")
    return lines
