"""Deterministic tree traversal that reports I/O failures and never follows links."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TreeEntry:
    path: Path
    mode: int
    file_attributes: int

    @classmethod
    def from_stat(cls, path: Path, details: os.stat_result) -> TreeEntry:
        return cls(path, details.st_mode, getattr(details, "st_file_attributes", 0))

    @property
    def is_file(self) -> bool:
        return stat.S_ISREG(self.mode) and not self.is_symlink

    @property
    def is_dir(self) -> bool:
        return stat.S_ISDIR(self.mode) and not self.is_symlink

    @property
    def is_symlink(self) -> bool:
        # Windows junctions have directory mode with a reparse attribute.
        return stat.S_ISLNK(self.mode) or bool(
            self.file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
        )


def walk_tree(root: Path, *, skip_names: frozenset[str] = frozenset()) -> Iterator[TreeEntry]:
    """Yield entries in path order, classifying each with no-follow stat."""

    def children(directory: Path) -> list[TreeEntry]:
        with os.scandir(directory) as entries:
            return sorted(
                (
                    TreeEntry.from_stat(Path(entry.path), entry.stat(follow_symlinks=False))
                    for entry in entries
                    if entry.name not in skip_names
                ),
                key=lambda entry: entry.path,
                reverse=True,
            )

    first = TreeEntry.from_stat(root, root.lstat())
    if not first.is_dir:
        yield first
        return
    pending = children(root)
    while pending:
        entry = pending.pop()
        yield entry
        if entry.is_dir:
            pending.extend(children(entry.path))
