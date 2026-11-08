"""Filesystem edit behavior and its owned helpers."""

# pyright: reportPrivateUsage=false

import difflib
from io import StringIO
from pathlib import Path
from threading import Event
from typing import Any

from cirno_core.agent.tools.base import ToolResult, tool_parameters
from cirno_core.agent.tools.filesystem.base import FileTool
from cirno_core.agent.tools.filesystem.edit_io import (
    MAX_EDIT_BYTES,
    PreparedEdit,
    check_edit_size,
    read_edit_snapshot,
)
from cirno_core.agent.tools.filesystem.matching import (
    _best_window,
    _find_matches,
    _preserve_quote_style,
    _reindent_like_match,
)
from cirno_core.agent.tools.filesystem.selection import select_matches
from cirno_core.agent.tools.filesystem.workers import run_file_operation
from cirno_core.agent.tools.schema import (
    BooleanSchema,
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)
from cirno_core.utils.file_edit_events import FileDiff, FileEditResult, display_file_edit_path


@tool_parameters(
    tool_parameters_schema(
        path=StringSchema("The file path to edit"),
        old_text=StringSchema("The text to find and replace; copy it from read_file."),
        new_text=StringSchema(
            "The replacement text; must differ from old_text for an existing file."
        ),
        replace_all=BooleanSchema(description="Replace all occurrences (default false)"),
        occurrence=IntegerSchema(
            description="Optional 1-based occurrence to replace when old_text appears multiple times.",
            minimum=1,
            nullable=True,
        ),
        line_hint=IntegerSchema(
            description=(
                "Optional exact 1-based target line copied from read_file. "
                "The selected old_text match must cover this line."
            ),
            minimum=1,
            nullable=True,
        ),
        expected_replacements=IntegerSchema(
            description="Optional guard for the number of replacements that must be made.",
            minimum=1,
            nullable=True,
        ),
        required=["path", "old_text", "new_text"],
    )
)
class EditFileTool(FileTool):
    """Edit a file by replacing text with fallback matching."""

    _scopes = {"core", "subagent", "memory"}

    _MARKDOWN_EXTS = frozenset({".md", ".mdx", ".markdown"})

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "Perform a small, exact replacement in one file. "
            "Prefer apply_patch for multi-file, structural, or generated edits. "
            "occurrence, line_hint, and replace_all=true are mutually exclusive."
        )

    @staticmethod
    def _strip_trailing_ws(text: str, *, preserve_last_line: bool = False) -> str:
        """Strip line-ending whitespace, except a final fragment that continues inline."""
        lines = text.split("\n")
        return "\n".join(
            line if preserve_last_line and i == len(lines) - 1 else line.rstrip()
            for i, line in enumerate(lines)
        )

    def _format_summary(
        self,
        resolved_path: Path,
        before: str,
        after: str,
        *,
        created: bool = False,
    ) -> FileEditResult:
        diff = FileDiff.from_text(before, after)
        added, deleted = diff.added, diff.deleted
        action = "add" if created else "update"
        stats = f" (+{added}/-{deleted})" if added or deleted else ""
        path = display_file_edit_path(resolved_path, self._display_workspace())
        text = f"Patch applied:\n- {action} {path}{stats}"
        return FileEditResult(text, {resolved_path: diff})

    async def execute(
        self,
        path: str | None = None,
        old_text: str | None = None,
        new_text: str | None = None,
        replace_all: bool = False,
        occurrence: int | None = None,
        line_hint: int | None = None,
        expected_replacements: int | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            prepared = await run_file_operation(
                lambda cancelled: self._prepare_edit(
                    path=path,
                    old_text=old_text,
                    new_text=new_text,
                    replace_all=replace_all,
                    occurrence=occurrence,
                    line_hint=line_hint,
                    expected_replacements=expected_replacements,
                    cancelled=cancelled,
                )
            )
            if isinstance(prepared, PreparedEdit):
                await run_file_operation(prepared.commit)
                self._file_states.record_write(prepared.path)
                return prepared.result
            return prepared
        except PermissionError as exc:
            return ToolResult.error(f"Error: {exc}")
        except Exception as exc:
            return ToolResult.error(f"Error editing file: {exc}")

    def _prepared(self, path: Path, before: str | None, after: str) -> PreparedEdit:
        return PreparedEdit(
            path,
            before,
            after,
            self._format_summary(
                path,
                before or "",
                after,
                created=before is None,
            ),
        )

    def _prepare_edit(
        self,
        *,
        path: str | None,
        old_text: str | None,
        new_text: str | None,
        replace_all: bool,
        occurrence: int | None,
        line_hint: int | None,
        expected_replacements: int | None,
        cancelled: Event,
    ) -> str | PreparedEdit:
        try:
            if not path:
                raise ValueError("Unknown path")
            if old_text is None:
                raise ValueError("Unknown old_text")
            if new_text is None:
                raise ValueError("Unknown new_text")
            if occurrence is not None and occurrence < 1:
                return ToolResult.error("Error: occurrence must be >= 1.")
            if line_hint is not None and line_hint < 1:
                return ToolResult.error("Error: line_hint must be >= 1.")
            if expected_replacements is not None and expected_replacements < 1:
                return ToolResult.error("Error: expected_replacements must be >= 1.")

            fp = self._resolve_write(path)
            check_edit_size(new_text, fp)
            file_exists = fp.exists()
            if file_exists and old_text == new_text:
                return ToolResult.error("Error: new_text must be different from old_text.")

            # Create-file semantics: old_text='' + file doesn't exist → create
            if not file_exists:
                if old_text == "":
                    return self._prepared(fp, None, new_text)
                return self._file_not_found_msg(path, fp)

            original = read_edit_snapshot(fp)

            # Create-file: old_text='' but file exists and not empty → reject
            if old_text == "":
                content = original
                if content.strip():
                    return ToolResult.error(
                        f"Error: Cannot create file — {path} already exists and is not empty."
                    )
                return self._prepared(fp, content, new_text)

            uses_crlf = "\r\n" in original
            content = original.replace("\r\n", "\n")
            norm_old = old_text.replace("\r\n", "\n")
            selection = select_matches(
                _find_matches(content, norm_old),
                occurrence=occurrence,
                line_hint=line_hint,
                cancelled=cancelled,
            )
            count = selection.count
            if not count:
                return self._not_found_msg(old_text, content, path)
            if replace_all and occurrence is not None:
                return ToolResult.error("Error: occurrence cannot be used with replace_all=true.")
            if replace_all and line_hint is not None:
                return ToolResult.error("Error: line_hint cannot be used with replace_all=true.")
            if occurrence is not None and line_hint is not None:
                return ToolResult.error("Error: line_hint cannot be used with occurrence.")
            if occurrence is not None and occurrence > count:
                return ToolResult.error(
                    f"Error: occurrence {occurrence} is out of range; "
                    f"old_text appears {count} time(s)."
                )
            if count > 1 and not replace_all and occurrence is None and line_hint is None:
                preview = ", ".join(f"line {n}" for n in selection.preview_lines)
                if count > 3:
                    preview += ", ..."
                location_hint = f" at {preview}" if preview else ""
                return (
                    f"Warning: old_text appears {count} times{location_hint}. "
                    "Provide more context, set occurrence to choose one match, "
                    "or set replace_all=true."
                )

            norm_new = new_text.replace("\r\n", "\n")

            if replace_all:
                selected = _find_matches(content, norm_old)
            elif occurrence is not None:
                selected = iter(selection.chosen)
            elif line_hint is not None:
                candidates = selection.chosen
                if not candidates:
                    locations = ", ".join(f"line {line}" for line in selection.preview_lines)
                    if count > 3:
                        locations += ", ..."
                    return ToolResult.error(
                        f"Error: line_hint {line_hint} does not match the old_text location. "
                        f"old_text appears at {locations}. Re-read the intended region and "
                        "copy old_text that covers the target line."
                    )
                if len(candidates) > 1:
                    return ToolResult.error(
                        f"Error: line_hint {line_hint} is ambiguous; "
                        f"old_text appears {len(candidates)} times on that line."
                    )
                selected = iter(candidates)
            else:
                selected = iter(selection.chosen)
            replacements = count if replace_all else len(selection.chosen)
            if expected_replacements is not None and replacements != expected_replacements:
                return ToolResult.error(
                    f"Error: expected {expected_replacements} replacements but "
                    f"would make {replacements}."
                )
            output = StringIO()
            cursor = 0
            cached_line_end, last_non_whitespace = -1, -1
            for index, match in enumerate(selected):
                if index % 1024 == 0 and cancelled.is_set():
                    raise InterruptedError("File edit preparation cancelled")
                if match.start < cursor:
                    return ToolResult.error(
                        "Error: replacements overlap; choose one occurrence or provide more context."
                    )
                replacement = norm_new
                # Preserve separator whitespace when the remaining line has content.
                # Markdown keeps all trailing whitespace for hard line breaks.
                if fp.suffix.lower() not in self._MARKDOWN_EXTS:
                    if match.end > cached_line_end:
                        cached_line_end = content.find("\n", match.end)
                        if cached_line_end == -1:
                            cached_line_end = len(content)
                        last_non_whitespace = match.end + len(
                            content[match.end : cached_line_end].rstrip()
                        )
                    replacement = self._strip_trailing_ws(
                        replacement,
                        preserve_last_line=match.end < last_non_whitespace,
                    )
                replacement = _preserve_quote_style(norm_old, match.text, replacement)
                replacement = _reindent_like_match(norm_old, match.text, replacement)

                # Only consume the trailing newline when deleting complete lines;
                # inline suffix deletions must preserve the remaining line boundary.
                end = match.end
                if (
                    replacement == ""
                    and (match.start == 0 or content[match.start - 1] == "\n")
                    and not match.text.endswith("\n")
                    and content[end : end + 1] == "\n"
                ):
                    end += 1

                output.write(content[cursor : match.start])
                output.write(replacement)
                if output.tell() > MAX_EDIT_BYTES:
                    raise ValueError("Edited content exceeds the 2 MiB limit; split the edit.")
                cursor = end
            output.write(content[cursor:])
            new_content = output.getvalue()
            if uses_crlf:
                new_content = new_content.replace("\n", "\r\n")

            check_edit_size(new_content, fp)
            return self._prepared(fp, original, new_content)
        except PermissionError as e:
            return ToolResult.error(f"Error: {e}")
        except Exception as e:
            return ToolResult.error(f"Error editing file: {e}")

    def _file_not_found_msg(self, path: str, fp: Path) -> str:
        """Build an error message with 'Did you mean ...?' suggestions."""
        parent = fp.parent
        suggestions: list[str] = []
        if parent.is_dir():
            siblings = [f.name for f in parent.iterdir() if f.is_file()]
            close = difflib.get_close_matches(fp.name, siblings, n=3, cutoff=0.6)
            suggestions = [str(parent / c) for c in close]
        parts = [f"Error: File not found: {path}"]
        if suggestions:
            parts.append("Did you mean: " + ", ".join(suggestions) + "?")
        return ToolResult.error("\n".join(parts))

    @staticmethod
    def _not_found_msg(old_text: str, content: str, path: str) -> str:
        if (content.count("\n") + 1) * (old_text.count("\n") + 1) > 1_000_000:
            return ToolResult.error(
                f"Error: old_text not found in {path}. Similarity hints would scan too many line windows. "
                "Copy exact text from files.read and try again."
            )
        best_ratio, best_start, best_window_lines, hints = _best_window(old_text, content)
        if best_ratio > 0.5:
            diff = "\n".join(
                difflib.unified_diff(
                    old_text.splitlines(keepends=True),
                    best_window_lines,
                    fromfile="old_text (provided)",
                    tofile=f"{path} (actual, line {best_start + 1})",
                    lineterm="",
                )
            )
            hint_text = ""
            if hints:
                hint_text = "\nPossible cause: " + ", ".join(hints) + "."
            return ToolResult.error(
                f"Error: old_text not found in {path}."
                f"{hint_text}\nBest match ({best_ratio:.0%} similar) at line {best_start + 1}:\n{diff}"
            )

        if hints:
            return ToolResult.error(
                f"Error: old_text not found in {path}. "
                f"Possible cause: {', '.join(hints)}. "
                "Copy the exact text from read_file and try again."
            )
        return ToolResult.error(
            f"Error: old_text not found in {path}. No similar text found. Verify the file content."
        )
