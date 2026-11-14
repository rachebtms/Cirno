"""Filesystem read behavior and its owned helpers."""

# pyright: reportPrivateUsage=false

import mimetypes
from pathlib import Path
from threading import Event
from typing import Any

from cirno_core.agent.tools.base import ToolResult, tool_parameters
from cirno_core.agent.tools.context import current_request_context
from cirno_core.agent.tools.filesystem.base import FileTool
from cirno_core.agent.tools.filesystem.text_page import read_text_page, text_encoding
from cirno_core.agent.tools.filesystem.workers import run_file_operation
from cirno_core.agent.tools.schema import (
    BooleanSchema,
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)
from cirno_core.utils.atomic_file import open_atomic_snapshot
from cirno_core.utils.model_messages import build_image_content_blocks, detect_image_mime

_BLOCKED_DEVICE_PATHS = frozenset(
    {
        "/dev/zero",
        "/dev/random",
        "/dev/urandom",
        "/dev/full",
        "/dev/stdin",
        "/dev/stdout",
        "/dev/stderr",
        "/dev/tty",
        "/dev/console",
        "/dev/fd/0",
        "/dev/fd/1",
        "/dev/fd/2",
    }
)


def image_input_error() -> ToolResult | None:
    request = current_request_context()
    if request and request.runtime and request.runtime.provider.media_capabilities.image is False:
        return ToolResult.error("The selected model has image input disabled. Choose an image-capable model or update its capabilities in Settings.")
    return None


def _is_blocked_device(path: str | Path) -> bool:
    """Check if path is a blocked device that could hang or produce infinite output."""
    import re

    raw = str(path)

    resolved = str(Path(raw).resolve())

    if raw in _BLOCKED_DEVICE_PATHS or resolved in _BLOCKED_DEVICE_PATHS:
        return True
    if re.match(r"/proc/\d+/fd/[012]$", raw) or re.match(r"/proc/self/fd/[012]$", raw):
        return True
    if re.match(r"/proc/\d+/fd/[012]$", resolved) or re.match(r"/proc/self/fd/[012]$", resolved):
        return True

    # Check if resolved path starts with /dev/ (covers symlinks to devices)
    if resolved.startswith("/dev/"):
        return True
    return False


def _builtin_skill_read_path(path: str) -> Path | None:
    """Map workspace-relative skills/<name>/... reads onto bundled skills."""
    from cirno_core.skills.metadata import BUILTIN_SKILLS_DIR

    requested = Path(path)
    if requested.is_absolute():
        return None
    parts = requested.parts
    if len(parts) < 2 or parts[0] != "skills":
        return None
    root = BUILTIN_SKILLS_DIR.resolve()
    candidate = (root / Path(*parts[1:])).resolve()
    if candidate != root and root not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


@tool_parameters(
    tool_parameters_schema(
        path=StringSchema("The file path to read"),
        offset=IntegerSchema(
            description="1-based text or extracted-document line (default 1)",
            minimum=1,
        ),
        limit=IntegerSchema(
            description="Maximum lines to return (default 2000)",
            minimum=1,
        ),
        pages=StringSchema("PDF page number or range, e.g. '7' or '1-5' (max 20 pages)"),
        force=BooleanSchema(
            description="Return an unchanged range again",
            default=False,
        ),
        required=["path"],
    )
)
class ReadFileTool(FileTool):
    """Read file contents with optional line-based pagination."""

    _scopes = {"core", "subagent", "memory"}

    _MAX_CHARS = 128_000
    _MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024
    _MAX_IMAGE_SIZE_BYTES = 6 * 1024 * 1024
    _DEFAULT_LIMIT = 2000
    _MAX_PDF_PAGES = 20

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read text, images, PDFs, and Office documents by path. "
            "Text is line-numbered; use offset/limit or pages for targeted ranges."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(
        self,
        path: str | None = None,
        offset: int = 1,
        limit: int | None = None,
        pages: str | None = None,
        force: bool = False,
        **kwargs: Any,
    ) -> Any:
        return await run_file_operation(
            lambda cancelled: self._execute_sync(
                path=path,
                offset=offset,
                limit=limit,
                pages=pages,
                force=force,
                cancelled=cancelled,
            )
        )

    def _execute_sync(
        self,
        *,
        path: str | None = None,
        offset: int = 1,
        limit: int | None = None,
        pages: str | None = None,
        force: bool = False,
        cancelled: Event,
    ) -> Any:
        try:
            if not path:
                return ToolResult.error("Error reading file: Unknown path")

            # Device path blacklist
            if _is_blocked_device(path):
                return ToolResult.error(
                    f"Error: Reading {path} is blocked (device path that could hang or produce infinite output)."
                )

            fp = self._resolve_read(path)
            if not fp.exists():
                fp = _builtin_skill_read_path(path) or fp
            if _is_blocked_device(fp):
                return ToolResult.error(
                    f"Error: Reading {fp} is blocked (device path that could hang or produce infinite output)."
                )
            if not fp.exists():
                return ToolResult.error(f"Error: File not found: {path}")
            if not fp.is_file():
                return ToolResult.error(f"Error: Not a file: {path}")

            file_size = fp.stat().st_size
            if file_size > self._MAX_FILE_SIZE_BYTES:
                size_mib = file_size / (1024 * 1024)
                max_mib = self._MAX_FILE_SIZE_BYTES // (1024 * 1024)
                return ToolResult.error(
                    f"Error: File too large to read ({size_mib:.1f} MiB). Maximum is {max_mib} MiB."
                )

            # PDF support
            if fp.suffix.lower() == ".pdf":
                return self._read_pdf(fp, pages)

            # Office document support
            if fp.suffix.lower() in {".docx", ".xlsx", ".pptx"}:
                return self._read_office_doc(fp, offset, limit)

            with open_atomic_snapshot(fp) as source:
                header = source.read(32)
            if not header:
                return f"(Empty file: {path})"
            mime = detect_image_mime(header) or mimetypes.guess_type(path)[0]
            if mime and mime.startswith("image/"):
                if error := image_input_error():
                    return error
                if file_size > self._MAX_IMAGE_SIZE_BYTES:
                    return ToolResult.error(
                        "Image exceeds the 6 MiB inline read limit; resize it before reading."
                    )
                with open_atomic_snapshot(fp) as source:
                    raw = source.read(self._MAX_IMAGE_SIZE_BYTES + 1)
                if len(raw) > self._MAX_IMAGE_SIZE_BYTES:
                    return ToolResult.error(
                        "Image grew beyond the 6 MiB inline read limit; resize it before reading."
                    )
                return build_image_content_blocks(raw, mime, str(fp), f"(Image file: {path})")
            if limit is not None and limit < 1:
                raise ValueError("limit must be at least 1")
            offset = max(1, offset)
            options = dict(
                offset=offset,
                limit=limit or self._DEFAULT_LIMIT,
                max_chars=self._MAX_CHARS,
                max_bytes=self._MAX_FILE_SIZE_BYTES,
                cancelled=cancelled,
            )
            encoding = text_encoding(header)
            try:
                page = read_text_page(fp, encoding=encoding, **options)
            except UnicodeDecodeError:
                from cirno_core.utils.document import _is_text_extension

                if encoding != "utf-8-sig" or not _is_text_extension(fp.suffix.lower()):
                    return ToolResult.error(
                        f"Error: Cannot read binary file {path} (MIME: {mime or 'unknown'}). "
                        "Only supported text files and images can be read."
                    )
                page = read_text_page(fp, encoding="latin-1", **options)
            total, end = page.total_lines, page.end_line
            content_hash = page.content_hash
            if not total:
                return f"(Empty file: {path})"
            if offset > total:
                return ToolResult.error(
                    f"Error: offset {offset} is beyond end of file ({total} lines)"
                )
            if not force and self._file_states.is_unchanged(
                fp,
                offset=offset,
                limit=limit,
                content_hash=content_hash,
            ):
                return f"[File unchanged since last read: {path}]"
            result = page.text
            if page.truncated_line:
                result += (
                    f"\n\n(Line {offset} truncated; its remaining characters are not shown. "
                    "Use exec with a targeted command to inspect the omitted content.)"
                )
            if end < total:
                result += f"\n\n(Showing lines {offset}-{end} of {total}. Use offset={end + 1} to continue.)"
            else:
                result += f"\n\n(End of file — {total} lines total)"
            if cancelled.is_set():
                raise InterruptedError("File read cancelled")
            self._file_states.record_read(
                fp,
                offset=offset,
                limit=limit,
                content_hash=content_hash,
                result=result,
            )
            return result
        except PermissionError as e:
            return ToolResult.error(f"Error: {e}")
        except Exception as e:
            return ToolResult.error(f"Error reading file: {e}")

    def _read_pdf(self, fp: Path, pages: str | None) -> str:
        from cirno_core.utils.document import PdfPageRangeError, PdfSafetyError, extract_pdf_pages

        try:
            extraction = extract_pdf_pages(
                fp,
                pages=pages,
                max_pages=self._MAX_PDF_PAGES,
                max_chars=self._MAX_CHARS,
            )
        except PdfPageRangeError as e:
            return ToolResult.error(f"Error: Invalid page range '{pages}': {e!s}.")
        except PdfSafetyError as e:
            return ToolResult.error(f"Error reading PDF: {e}")
        except Exception as e:
            return ToolResult.error(f"Error reading PDF: {e}")

        if not extraction.text:
            return f"(PDF has no extractable text: {fp})"

        result = extraction.text
        if extraction.truncated:
            result += (
                f"\n\n(Page {extraction.end_page + 1} was truncated; "
                "the remaining text on this page is not shown.)"
            )
        if extraction.end_page < extraction.total_pages - 1:
            next_start = extraction.end_page + 2
            next_end = min(extraction.end_page + 1 + self._MAX_PDF_PAGES, extraction.total_pages)
            result += (
                f"\n\n(Showing pages {extraction.start_page + 1}-{extraction.end_page + 1} "
                f"of {extraction.total_pages}. Use pages='{next_start}-{next_end}' to continue.)"
            )
        return result

    def _read_office_doc(
        self,
        fp: Path,
        offset: int,
        limit: int | None,
    ) -> str:
        from cirno_core.utils.document import open_document_line_source

        offset = max(1, offset)
        requested_limit = limit or self._DEFAULT_LIMIT
        source_iterator = None
        try:
            source = open_document_line_source(fp)
            if source is None:
                return ToolResult.error(f"Error: Unsupported file format: {fp.suffix}")
            source_iterator = source.lines
            numbered: list[str] = []
            output_chars = 0
            total_seen = 0
            end = offset - 1
            has_more = False
            line_was_clipped = False

            for line in source_iterator:
                total_seen = line.extracted_line
                if line.extracted_line < offset:
                    continue
                if len(numbered) >= requested_limit:
                    has_more = True
                    break

                rendered = f"{line.extracted_line}| {line.text}"
                extra = 1 if numbered else 0
                if output_chars + extra + len(rendered) > self._MAX_CHARS:
                    if numbered:
                        has_more = True
                        break
                    prefix = f"{line.extracted_line}| "
                    available = max(0, self._MAX_CHARS - len(prefix) - 3)
                    rendered = f"{prefix}{line.text[:available]}..."
                    line_was_clipped = True
                    has_more = True
                numbered.append(rendered)
                output_chars += extra + len(rendered)
                end = line.extracted_line
                if line_was_clipped:
                    break

            if not numbered:
                if total_seen == 0:
                    return f"({fp.suffix.upper().lstrip('.')} has no extractable text: {fp})"
                return ToolResult.error(
                    f"Error: offset {offset} is beyond end of extracted document "
                    f"({total_seen} lines)"
                )

            output = "\n".join(numbered)
            if has_more:
                if line_was_clipped:
                    output += (
                        "\n\n(Document text truncated at ~128K chars; line clipped. "
                        f"Use offset={end + 1} to continue.)"
                    )
                else:
                    output += (
                        f"\n\n(Showing extracted lines {offset}-{end}. "
                        f"Use offset={end + 1} to continue.)"
                    )
            else:
                output += f"\n\n(End of document — {total_seen} extracted lines total)"
            return output
        except Exception as e:
            return ToolResult.error(f"Error reading {fp.suffix.upper()} file: {e!s}")
        finally:
            close = getattr(source_iterator, "close", None)
            if close is not None:
                close()
