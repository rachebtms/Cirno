"""Ordered path discovery without following directory symlinks."""

import heapq
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from cirno_core.agent.tools.search.base import SearchTool
from cirno_core.agent.tools.search.budget import SearchBudget


@dataclass(slots=True)
class PathEntry:
    path: Path
    rel_path: str
    display_path: str
    name: str
    is_dir: bool


class PathSearchTool(SearchTool):
    def _entry(self, path: Path, root: Path, *, is_dir: bool) -> PathEntry:
        display_path = self._display_path(path, root)
        return PathEntry(
            path=path,
            rel_path=path.relative_to(root).as_posix(),
            display_path=display_path,
            name=path.name,
            is_dir=is_dir,
        )

    def _push_directory_entries(
        self,
        directory: Path,
        root: Path,
        frontier: list[tuple[str, int, PathEntry]],
        sequence: int,
        budget: SearchBudget,
    ) -> int:
        for path, is_dir in self._directory_entries(directory, budget):
            entry = self._entry(path, root, is_dir=is_dir)
            sort_path = entry.display_path + ("/" if is_dir else "")
            heapq.heappush(frontier, (sort_path, sequence, entry))
            sequence += 1
        return sequence

    def _iter_paths(
        self,
        root: Path,
        *,
        include_dirs: bool,
        budget: SearchBudget,
    ) -> Iterable[PathEntry]:
        budget.checkpoint()
        if root.is_file():
            budget.visit_path()
            yield self._entry(root, root.parent, is_dir=False)
            return

        if include_dirs:
            yield self._entry(root, root, is_dir=True)

        frontier: list[tuple[str, int, PathEntry]] = []
        sequence = self._push_directory_entries(root, root, frontier, 0, budget)
        while frontier:
            budget.checkpoint()
            _, _, entry = heapq.heappop(frontier)
            if entry.is_dir:
                if include_dirs:
                    yield entry
                sequence = self._push_directory_entries(
                    entry.path,
                    root,
                    frontier,
                    sequence,
                    budget,
                )
            else:
                yield entry
