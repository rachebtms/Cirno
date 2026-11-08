"""Apply file edits by providing structured edit instructions."""

from __future__ import annotations

from threading import Event
from typing import Any, cast

from cirno_core.agent.tools.base import ToolResult, tool_parameters
from cirno_core.agent.tools.filesystem.base import FileTool
from cirno_core.agent.tools.filesystem.patch_plan import PatchPlan
from cirno_core.agent.tools.filesystem.workers import run_file_operation
from cirno_core.agent.tools.schema import (
    ArraySchema,
    BooleanSchema,
    ObjectSchema,
    StringSchema,
    tool_parameters_schema,
)
from cirno_core.utils.file_edit_events import FileDiff, FileEditResult, display_file_edit_path


@tool_parameters(
    tool_parameters_schema(
        edits=ArraySchema(
            items=ObjectSchema(
                path=StringSchema(
                    "Path to the file to edit. Relative paths resolve against the "
                    "workspace; absolute paths and '..' obey the workspace access policy."
                ),
                action=StringSchema(
                    "replace updates a unique text match; add creates a file or appends to an existing one.",
                    enum=["replace", "add"],
                ),
                old_text=StringSchema(
                    "Exact text occurring once in the file; required for replace.",
                    nullable=True,
                ),
                new_text=StringSchema(
                    "Text to replace with or append. Required for replace and add.",
                    nullable=True,
                ),
                required=["path", "action"],
            ),
            description="File edits, applied in order.",
            min_items=1,
            max_items=20,
        ),
        dry_run=BooleanSchema(
            description="Validate and summarize the patch without writing files.",
            default=False,
        ),
        required=["edits"],
    )
)
class ApplyPatchTool(FileTool):
    """Apply file edits by providing structured edit instructions."""

    _scopes = {"core", "subagent"}

    @property
    def name(self) -> str:
        return "apply_patch"

    @property
    def description(self) -> str:
        return (
            "Default tool for code edits, including multi-file changes. "
            "Returns a file-change summary. "
            "Use edit_file only for small exact replacements on a single file."
        )

    async def execute(
        self,
        edits: list[object] | None = None,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> str:
        try:
            if not edits:
                raise ValueError("must provide edits")

            plan, result = await run_file_operation(
                lambda cancelled: self._prepare(edits, cancelled)
            )
            if dry_run:
                return str(result).replace("Patch applied:", "Patch dry-run succeeded:", 1)
            await run_file_operation(plan.commit)
            for path in plan.writes:
                self._file_states.record_write(path)
            return result
        except PermissionError as exc:
            return ToolResult.error(f"Error: {exc}")
        except Exception as exc:
            return ToolResult.error(f"Error applying patch: {exc}")

    def _prepare(self, edits: list[object], cancelled: Event) -> tuple[PatchPlan, FileEditResult]:
        plan = PatchPlan()
        for edit_value in edits:
            if cancelled.is_set():
                raise InterruptedError("Patch preparation cancelled")
            if not isinstance(edit_value, dict):
                raise ValueError("each edit must be an object")
            edit = cast(dict[str, Any], edit_value)
            path = edit.get("path")
            if not isinstance(path, str) or not path.strip() or "\0" in path:
                raise ValueError("path required for edit")
            action = edit.get("action")
            if not isinstance(action, str):
                raise ValueError(f"action required for edit: {path}")
            source = self._resolve_write(path.strip())
            plan.add(source, edit)

        diffs = {
            source: FileDiff.from_text(plan.originals[source] or "", content)
            for source, content in plan.writes.items()
        }
        summaries: list[str] = []
        for source, diff in diffs.items():
            action_name = plan.actions[source]
            path = display_file_edit_path(source, self._display_workspace())
            added, deleted = diff.added, diff.deleted
            stats = f" (+{added}/-{deleted})" if added or deleted else ""
            summaries.append(f"- {action_name} {path}{stats}")

        return plan, FileEditResult("Patch applied:\n" + "\n".join(summaries), diffs)
