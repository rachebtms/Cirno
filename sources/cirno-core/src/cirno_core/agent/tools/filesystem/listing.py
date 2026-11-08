"""Filesystem listing behavior and its owned helpers."""

# pyright: reportPrivateUsage=false

from typing import Any

from cirno_core.agent.tools.base import ToolResult, tool_parameters
from cirno_core.agent.tools.filesystem.base import FileTool
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

            if recursive:
                for item in sorted(dp.rglob("*")):
                    rel = item.relative_to(dp)
                    if any(p in self._IGNORE_DIRS for p in rel.parts):
                        continue
                    total += 1
                    if len(items) < cap:
                        items.append(f"{rel}/" if item.is_dir() else str(rel))
            else:
                for item in sorted(dp.iterdir()):
                    if item.name in self._IGNORE_DIRS:
                        continue
                    total += 1
                    if len(items) < cap:
                        pfx = "📁 " if item.is_dir() else "📄 "
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
