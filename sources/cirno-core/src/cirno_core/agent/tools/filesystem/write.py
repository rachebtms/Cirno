"""Filesystem write behavior and its owned helpers."""

# pyright: reportPrivateUsage=false

from threading import Event
from typing import Any

from cirno_core.agent.tools.base import ToolResult, tool_parameters
from cirno_core.agent.tools.filesystem.base import FileTool
from cirno_core.agent.tools.filesystem.workers import run_file_operation
from cirno_core.agent.tools.schema import (
    StringSchema,
    tool_parameters_schema,
)
from cirno_core.utils.atomic_file import atomic_write_text
from cirno_core.utils.file_transactions import file_write_transaction


@tool_parameters(
    tool_parameters_schema(
        path=StringSchema("The file path to write to"),
        content=StringSchema("The content to write"),
        required=["path", "content"],
    )
)
class WriteFileTool(FileTool):
    """Write content to a file."""

    _scopes = {"core", "subagent", "memory"}

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Create a file or replace an entire file. "
            "Overwrites existing files and creates parent directories. "
            "Prefer apply_patch for partial edits."
        )

    async def execute(
        self, path: str | None = None, content: str | None = None, **kwargs: Any
    ) -> str:
        try:
            if not path:
                raise ValueError("Unknown path")
            if content is None:
                raise ValueError("Unknown content")
            fp = self._resolve_write(path)
            def write(cancelled: Event) -> None:
                with file_write_transaction([fp], cancelled=cancelled):
                    atomic_write_text(fp, content)
            await run_file_operation(write)
            self._file_states.record_write(fp)
            return f"Successfully wrote {len(content)} characters to {fp}"
        except PermissionError as e:
            return ToolResult.error(f"Error: {e}")
        except Exception as e:
            return ToolResult.error(f"Error writing file: {e}")
