"""Search bounded text and document streams with located match context."""

# pyright: reportIncompatibleMethodOverride=false

from __future__ import annotations

import asyncio
import stat
import threading
import time
from typing import Any, Iterable, Iterator

from cirno_core.agent.tools.base import ToolResult
from cirno_core.agent.tools.search.base import SearchTool
from cirno_core.agent.tools.search.budget import (
    SearchBudget,
    SearchBudgetExceededError,
    SearchCancelledError,
)
from cirno_core.agent.tools.search.content import ContentPage, MatchTooLargeError
from cirno_core.agent.tools.search.matching import SearchPattern
from cirno_core.agent.tools.search.paging import text_page
from cirno_core.agent.tools.search.patterns import glob_patterns, matches_glob, matches_type
from cirno_core.agent.tools.search.schema import grep_parameters
from cirno_core.agent.tools.search.sources import DOCUMENT_EXTENSIONS, open_source
from cirno_core.utils.document import LocatedDocumentLine, PdfPageRangeError

_DEFAULT_HEAD_LIMIT = 250


class GrepTool(SearchTool):
    """Search text and document contents using a regex-like pattern."""

    _scopes = {"core", "subagent"}

    _MAX_RENDERED_LINE_CHARS = 2_000
    _MAX_FILE_BYTES = 2_000_000
    _MAX_EXPLICIT_FILE_BYTES = 100_000_000

    @property
    def name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return (
            "Search text, PDF, DOCX, XLSX, and PPTX content. "
            "Returns matches with five context lines and source locators by default."
        )

    @property
    def read_only(self) -> bool:
        return True

    @property
    def parameters(self) -> dict[str, Any]:
        return grep_parameters()

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        glob: str | None = None,
        type: str | None = None,
        pages: str | None = None,
        case_insensitive: bool = False,
        fixed_strings: bool = False,
        output_mode: str = "content",
        context_before: int = 5,
        context_after: int = 5,
        max_matches: int | None = None,
        max_results: int | None = None,
        head_limit: int | None = None,
        offset: int = 0,
        **kwargs: Any,
    ) -> str:
        cancelled = threading.Event()
        try:
            return await asyncio.to_thread(
                self._execute_sync,
                pattern=pattern,
                path=path,
                glob=glob,
                type=type,
                pages=pages,
                case_insensitive=case_insensitive,
                fixed_strings=fixed_strings,
                output_mode=output_mode,
                context_before=context_before,
                context_after=context_after,
                max_matches=max_matches,
                max_results=max_results,
                head_limit=head_limit,
                offset=offset,
                cancelled=cancelled,
            )
        except asyncio.CancelledError:
            cancelled.set()
            raise

    def _execute_sync(
        self,
        *,
        pattern: str,
        path: str,
        glob: str | None,
        type: str | None,
        pages: str | None,
        case_insensitive: bool,
        fixed_strings: bool,
        output_mode: str,
        context_before: int,
        context_after: int,
        max_matches: int | None,
        max_results: int | None,
        head_limit: int | None,
        offset: int,
        cancelled: threading.Event,
    ) -> str:
        budget = SearchBudget(
            cancelled=cancelled,
            deadline=time.monotonic() + self._MAX_SCAN_SECONDS,
            max_paths=self._MAX_SCAN_PATHS,
        )

        def checked_lines(lines: Iterable[LocatedDocumentLine]) -> Iterable[LocatedDocumentLine]:
            for line in lines:
                budget.checkpoint()
                yield line

        try:
            budget.checkpoint()
            if glob:
                glob_patterns(glob)
            target = self._resolve(path or ".")
            if not target.exists():
                return ToolResult.error(f"Error: Path not found: {path}")
            if not (target.is_dir() or target.is_file()):
                return ToolResult.error(f"Error: Unsupported path: {path}")

            try:
                regex = SearchPattern(
                    pattern,
                    budget,
                    fixed_strings=fixed_strings,
                    case_insensitive=case_insensitive,
                )
            except ValueError as e:
                return ToolResult.error(f"Error: {e}")

            if head_limit is not None:
                limit = None if head_limit == 0 else head_limit
            elif output_mode == "content" and max_matches is not None:
                limit = max_matches
            elif output_mode != "content" and max_results is not None:
                limit = max_results
            else:
                limit = _DEFAULT_HEAD_LIMIT
            content_page = ContentPage(
                limit, offset, self._MAX_RESULT_CHARS, self._MAX_RENDERED_LINE_CHARS
            )
            skipped_binary = 0
            skipped_large = 0
            skipped_special = 0
            first_document_error: str | None = None
            document_error_count = 0
            document_continuations: list[str] = []
            counts: dict[str, int] = {}
            file_mtimes: dict[str, float] = {}
            root = target if target.is_dir() else target.parent
            max_file_bytes = (
                self._MAX_EXPLICIT_FILE_BYTES if target.is_file() else self._MAX_FILE_BYTES
            )

            for file_path in self._iter_files(target, budget):
                rel_path = file_path.relative_to(root).as_posix()
                if glob and not matches_glob(rel_path, file_path.name, glob):
                    continue
                if not matches_type(file_path.name, type):
                    continue
                display_path = self._display_path(file_path, root)

                readable_path = (
                    self._resolve_read(str(file_path)) if file_path.is_symlink() else file_path
                )
                file_stat = readable_path.stat()
                if not stat.S_ISREG(file_stat.st_mode):
                    skipped_special += 1
                    continue
                if file_stat.st_size > max_file_bytes:
                    skipped_large += 1
                    continue
                mtime = file_stat.st_mtime
                source_iterator: Iterator[LocatedDocumentLine] | None = None
                is_document = file_path.suffix.lower() in DOCUMENT_EXTENSIONS
                try:
                    source = open_source(readable_path, pages, max_file_bytes)
                    if source is None:
                        skipped_binary += 1
                        continue
                    source_iterator = source.lines
                    if source.continuation and len(document_continuations) < 10:
                        document_continuations.append(
                            f"({display_path}: continue PDF search with {source.continuation})"
                        )
                    source_lines = checked_lines(source_iterator)

                    file_had_match = False
                    if output_mode == "content":
                        content_page.scan(
                            display_path, source_lines, regex, context_before, context_after
                        )
                    else:
                        for line in source_lines:
                            if not line.searchable or regex.search(line.text) is None:
                                continue
                            file_had_match = True
                            if output_mode == "count":
                                counts[display_path] = counts.get(display_path, 0) + 1
                                continue
                            break
                except (SearchCancelledError, SearchBudgetExceededError, MatchTooLargeError):
                    raise
                except Exception as e:
                    if not is_document:
                        raise
                    if target.is_file():
                        if isinstance(e, PdfPageRangeError):
                            return ToolResult.error(
                                f"Error: Invalid PDF page range '{pages}': {e!s}."
                            )
                        return ToolResult.error(f"Error searching document {display_path}: {e!s}")
                    document_error_count += 1
                    if first_document_error is None:
                        first_document_error = f"{display_path}: {e!s}"
                    continue
                finally:
                    close = getattr(source_iterator, "close", None)
                    if close is not None:
                        close()
                if file_had_match:
                    file_mtimes[display_path] = mtime
                if content_page.stopped:
                    break

            no_matches = f"No matches found for pattern '{pattern}' in {path}"
            notes: list[str] = []
            if output_mode == "content":
                result, note = content_page.render(no_matches)
                if note:
                    notes.append(note)
            else:
                ordered_files = sorted(
                    file_mtimes,
                    key=lambda name: (-file_mtimes.get(name, 0.0), name),
                )
                entries = (
                    [f"{name}: {counts[name]}" for name in ordered_files]
                    if output_mode == "count"
                    else ordered_files
                )
                paged, truncated = text_page(entries, limit, offset, self._MAX_RESULT_CHARS)
                result = "\n".join(paged) if file_mtimes or counts else no_matches
                if truncated:
                    notes.append(
                        f"(pagination: limit={limit}, offset={offset}; "
                        f"use offset={offset + len(paged)} to continue)"
                    )
                elif offset > 0:
                    notes.append(f"(pagination: offset={offset})")
            if skipped_binary:
                notes.append(f"(skipped {skipped_binary} binary/non-UTF-8 files)")
            if skipped_large:
                notes.append(f"(skipped {skipped_large} large files)")
            if skipped_special:
                notes.append(f"(skipped {skipped_special} non-regular files)")
            if document_error_count:
                notes.append(
                    f"(could not search {document_error_count} documents; "
                    f"first document error: {first_document_error})"
                )
            notes.extend(document_continuations)
            if output_mode == "count" and counts:
                notes.append(f"(total matches: {sum(counts.values())} in {len(counts)} files)")
            if notes:
                result += "\n\n" + "\n".join(notes)
            return result
        except MatchTooLargeError as exc:
            return ToolResult.error(f"Error: {exc}")
        except SearchBudgetExceededError as exc:
            detail = (
                f"{self._MAX_SCAN_PATHS} paths"
                if str(exc) == "paths"
                else f"{self._MAX_SCAN_SECONDS:g} seconds"
            )
            return ToolResult.error(
                f"Error: grep scan exceeded {detail}; narrow path, glob, or type and retry."
            )
        except PermissionError as e:
            return ToolResult.error(f"Error: {e}")
        except Exception as e:
            return ToolResult.error(f"Error searching files: {e}")
