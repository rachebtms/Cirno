"""Workspace-aware search capabilities and shared scan policy."""

# pyright: reportPrivateUsage=false

import os
from contextlib import suppress
from pathlib import Path
from typing import Iterable

from cirno_core.agent.tools.filesystem import ListDirTool
from cirno_core.agent.tools.filesystem.base import FileTool
from cirno_core.agent.tools.search.budget import SearchBudget


class SearchTool(FileTool):
    _IGNORE_DIRS = ListDirTool._IGNORE_DIRS | {".worktrees", ".worktree", ".cirno"}
    _MAX_SCAN_PATHS = 500_000
    _MAX_SCAN_SECONDS = 30.0
    _MAX_RESULT_CHARS = 12_000

    @classmethod
    def _ignore_directory(cls, name: str) -> bool:
        return name in cls._IGNORE_DIRS or name.startswith(".verify-")

    def _display_path(self, target: Path, root: Path) -> str:
        workspace = self._display_workspace()
        if workspace:
            with suppress(ValueError):
                return target.relative_to(workspace).as_posix()
        return target.relative_to(root).as_posix()

    def _iter_files(self, root: Path, budget: SearchBudget) -> Iterable[Path]:
        if root.is_file():
            budget.visit_path()
            yield root
            return

        pending = [root]
        while pending:
            entries = self._directory_entries(pending.pop(), budget)
            pending.extend(sorted((path for path, is_dir in entries if is_dir), reverse=True))
            yield from sorted(path for path, is_dir in entries if not is_dir)

    def _directory_entries(self, directory: Path, budget: SearchBudget) -> list[tuple[Path, bool]]:
        budget.checkpoint()
        children: list[tuple[Path, bool]] = []
        with os.scandir(directory) as entries:
            for entry in entries:
                budget.visit_path()
                is_dir = entry.is_dir(follow_symlinks=False)
                if not is_dir and entry.is_symlink() and entry.is_dir():
                    continue
                if is_dir and self._ignore_directory(entry.name):
                    continue
                children.append((Path(entry.path), is_dir))
        return children
