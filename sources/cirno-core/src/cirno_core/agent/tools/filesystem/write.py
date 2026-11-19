"""Filesystem write behavior and its owned helpers."""

# pyright: reportPrivateUsage=false

from threading import Event
from typing import Any

from cirno_core.agent.tools.base import ToolResult, tool_parameters
from cirno_core.agent.tools.filesystem.base import FileTool
from cirno_core.agent.tools.filesystem.edit_io import publish_file_text
from cirno_core.agent.tools.filesystem.workers import run_file_operation
from cirno_core.agent.tools.schema import (
    StringSchema,
    tool_parameters_schema,
)
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
            def write(cancelled: Event):
                if cancelled.is_set():
                    raise InterruptedError("File write cancelled")
                # Resolution can snapshot an entire Skill tree. Keep that work
                # off the event loop together with the actual filesystem write.
                fp = self._resolve_write(path)
                with file_write_transaction([fp], cancelled=cancelled):
                    publish_file_text(fp, content)
                    self._finish_writes([fp])
                return fp
            fp = await run_file_operation(write)
            return f"Successfully wrote {len(content)} characters to {fp}"
        except PermissionError as e:
            return ToolResult.error(f"Error: {e}")
        except Exception as e:
            return ToolResult.error(f"Error writing file: {e}")
