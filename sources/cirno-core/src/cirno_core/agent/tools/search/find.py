"""Discover workspace files by query, glob and file type."""

# pyright: reportIncompatibleMethodOverride=false

from __future__ import annotations

import asyncio
import heapq
import threading
import time
from typing import Any, Iterator

from cirno_core.agent.tools.base import ToolResult
from cirno_core.agent.tools.search.budget import (
    SearchBudget,
    SearchBudgetExceededError,
    SearchCancelledError,
)
from cirno_core.agent.tools.search.paging import pagination_note, text_page
from cirno_core.agent.tools.search.paths import PathEntry, PathSearchTool
from cirno_core.agent.tools.search.patterns import (
    glob_patterns,
    matches_glob,
    matches_query,
    matches_type,
)
from cirno_core.agent.tools.search.schema import find_parameters

_DEFAULT_FILE_HEAD_LIMIT = 200


class FindFilesTool(PathSearchTool):
    """Find files by path fragment, glob, or type."""

    _scopes = {"core", "subagent"}

    @property
    def name(self) -> str:
        return "find_files"

    @property
    def description(self) -> str:
        return (
            "Find workspace paths by name, glob, or file type. "
            "Returns relative paths; skips dependencies, builds, worktrees and tool artifacts."
        )

    @property
    def read_only(self) -> bool:
        return True

    @property
    def parameters(self) -> dict[str, Any]:
        return find_parameters()

    @staticmethod
    def _matches_entry(
        entry: PathEntry,
        *,
        query: str | None,
        glob: str | None,
        file_type: str | None,
    ) -> bool:
        if glob and not matches_glob(entry.rel_path, entry.name, glob):
            return False
        if entry.is_dir:
            if file_type:
                return False
        elif not matches_type(entry.name, file_type):
            return False
        return matches_query(entry.display_path, query)

    async def execute(
        self,
        path: str = ".",
        query: str | None = None,
        glob: str | None = None,
        type: str | None = None,
        include_dirs: bool = False,
        sort: str = "path",
        head_limit: int | None = None,
        offset: int = 0,
        **kwargs: Any,
    ) -> str:
        cancelled = threading.Event()
        try:
            return await asyncio.to_thread(
                self._execute_sync,
                path=path,
                query=query,
                glob=glob,
                file_type=type,
                include_dirs=include_dirs,
                sort=sort,
                head_limit=head_limit,
                offset=offset,
                cancelled=cancelled,
            )
        except asyncio.CancelledError:
            cancelled.set()
            raise
        except PermissionError as e:
            return ToolResult.error(f"Error: {e}")
        except Exception as e:
            return ToolResult.error(f"Error finding files: {e}")

    def _execute_sync(
        self,
        *,
        path: str,
        query: str | None,
        glob: str | None,
        file_type: str | None,
        include_dirs: bool,
        sort: str,
        head_limit: int | None,
        offset: int,
        cancelled: threading.Event,
    ) -> str:
        started_at = time.monotonic()
        if cancelled.is_set():
            raise SearchCancelledError
        target = self._resolve(path or ".")
        if not target.exists():
            return ToolResult.error(f"Error: Path not found: {path}")
        if not (target.is_dir() or target.is_file()):
            return ToolResult.error(f"Error: Unsupported path: {path}")

        if glob:
            glob_patterns(glob)

        if sort not in {"path", "modified"}:
            return ToolResult.error("Error: sort must be 'path' or 'modified'")

        limit = (
            _DEFAULT_FILE_HEAD_LIMIT
            if head_limit is None
            else None
            if head_limit == 0
            else head_limit
        )
        budget = SearchBudget(
            cancelled=cancelled,
            deadline=started_at + self._MAX_SCAN_SECONDS,
            max_paths=self._MAX_SCAN_PATHS,
        )

        def matching_entries() -> Iterator[tuple[str, float]]:
            for entry in self._iter_paths(
                target,
                include_dirs=include_dirs,
                budget=budget,
            ):
                if not self._matches_entry(
                    entry,
                    query=query,
                    glob=glob,
                    file_type=file_type,
                ):
                    continue
                mtime = 0.0
                if sort == "modified":
                    mtime = entry.path.stat().st_mtime
                suffix = "/" if entry.is_dir else ""
                yield entry.display_path + suffix, mtime

        matches: list[tuple[str, float]]
        try:
            if sort == "modified":
                if limit is None:
                    matches = sorted(matching_entries(), key=lambda item: (-item[1], item[0]))
                else:
                    selection_size = offset + limit + 1
                    matches = heapq.nsmallest(
                        selection_size,
                        matching_entries(),
                        key=lambda item: (-item[1], item[0]),
                    )
            else:
                selection_size = None if limit is None else offset + limit + 1
                matches = []
                for match in matching_entries():
                    matches.append(match)
                    if selection_size is not None and len(matches) >= selection_size:
                        break
            budget.checkpoint()
        except SearchBudgetExceededError as exc:
            if str(exc) == "paths":
                detail = f"{self._MAX_SCAN_PATHS} paths"
            else:
                detail = f"{self._MAX_SCAN_SECONDS:g} seconds"
            return ToolResult.error(
                f"Error: find_files scan exceeded {detail}; "
                "narrow path, query, glob, or type and retry."
            )

        paths = [item[0] for item in matches]
        paged, truncated = text_page(paths, limit, offset, self._MAX_RESULT_CHARS)
        if not paged:
            return "No files found"

        result = "\n".join(paged)
        note = pagination_note(limit, offset, truncated)
        if note:
            result += "\n\n" + note
        if truncated:
            result += f"\n(use offset={offset + len(paged)} to continue)"
        return result
