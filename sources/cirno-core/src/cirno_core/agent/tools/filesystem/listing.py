"""Filesystem listing behavior and its owned helpers."""

# pyright: reportPrivateUsage=false

import os
from collections.abc import Iterator
from pathlib import Path
from threading import Event
from typing import Any

from cirno_core.agent.tools.base import ToolResult, tool_parameters
from cirno_core.agent.tools.filesystem.base import FileTool
from cirno_core.agent.tools.filesystem.workers import run_file_operation
from cirno_core.agent.tools.schema import (
    BooleanSchema,
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)


@tool_parameters(
    tool_parameters_schema(
        path=StringSchema("The directory path to list"),
        recursive=BooleanSchema(description="Recursively list all files (default false)"),
        max_entries=IntegerSchema(
            description="Maximum entries to return (default 200)",
            minimum=1,
        ),
        required=["path"],
    )
)
class ListDirTool(FileTool):
    """List directory contents with optional recursion."""

    _scopes = {"core", "subagent"}

    _DEFAULT_MAX = 200
    _IGNORE_DIRS = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".coverage",
        "htmlcov",
    }

    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return (
            "List directory contents, skipping common noise directories "
            "(.git, node_modules, __pycache__, etc.)."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(
        self,
        path: str | None = None,
        recursive: bool = False,
        max_entries: int | None = None,
        **kwargs: Any,
    ) -> str:
        return await run_file_operation(lambda cancelled: self._execute_sync(
            path=path, recursive=recursive, max_entries=max_entries, cancelled=cancelled,
        ))

    def _entries(self, directory: Path, cancelled: Event) -> list[tuple[Path, bool, bool]]:
        children: list[tuple[Path, bool, bool]] = []
        with os.scandir(directory) as entries:
            for entry in entries:
                if cancelled.is_set():
                    raise InterruptedError("Directory listing cancelled")
                if entry.name in self._IGNORE_DIRS:
                    continue
                children.append((Path(entry.path), entry.is_dir(), entry.is_dir(follow_symlinks=False)))
        return sorted(children)

    def _walk(self, root: Path, *, recursive: bool, cancelled: Event) -> Iterator[tuple[Path, bool]]:
        pending = [iter(self._entries(root, cancelled))]
        while pending:
            if cancelled.is_set():
                raise InterruptedError("Directory listing cancelled")
            try:
                path, is_dir, descend = next(pending[-1])
            except StopIteration:
                pending.pop()
                continue
            yield path, is_dir
            if recursive and descend:
                pending.append(iter(self._entries(path, cancelled)))

    def _execute_sync(
        self, *, path: str | None, recursive: bool, max_entries: int | None, cancelled: Event,
    ) -> str:
        try:
            if path is None:
                raise ValueError("Unknown path")
            dp = self._resolve(path)
            if not dp.exists():
                return ToolResult.error(f"Error: Directory not found: {path}")
            if not dp.is_dir():
                return ToolResult.error(f"Error: Not a directory: {path}")

            cap = max_entries or self._DEFAULT_MAX
            items: list[str] = []
            total = 0

            for item, is_dir in self._walk(dp, recursive=recursive, cancelled=cancelled):
                total += 1
                if len(items) >= cap:
                    continue
                if recursive:
                    rel = item.relative_to(dp)
                    items.append(f"{rel}/" if is_dir else str(rel))
                else:
                    pfx = "📁 " if is_dir else "📄 "
                    items.append(f"{pfx}{item.name}")

            if not items and total == 0:
                return f"Directory {path} is empty"

            result = "\n".join(items)
            if total > cap:
                result += f"\n\n(truncated, showing first {cap} of {total} entries)"
            return result
        except PermissionError as e:
            return ToolResult.error(f"Error: {e}")
        except Exception as e:
            return ToolResult.error(f"Error listing directory: {e}")
