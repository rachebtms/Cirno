"""Workspace-backed immutable overflow results."""

from __future__ import annotations

import hashlib
from pathlib import Path

from cirno_core.utils.atomic_file import atomic_write_text as _atomic_write_text
from cirno_core.utils.file_io import ensure_dir
from cirno_core.utils.text import safe_filename

_TOOL_RESULTS_DIR = ".cirno/tool-results"


def _render_tool_result_reference(
    reference_path: str,
    *,
    original_size: int,
    preview: str,
    truncated_preview: bool,
    max_chars: int | None = None,
) -> str:
    result = (
        f"[tool output persisted]\n"
        f"Full output saved to workspace path: {reference_path}\n"
        f"Original size: {original_size} chars\n"
        f"Preview:\n{preview}"
    )
    if truncated_preview:
        result += "\n...\nPreview is also truncated."
    result += "\nResult truncated. Read the saved file if you need the complete output."
    if max_chars and len(result) > max_chars:
        result = f"[truncated: {reference_path}]"
    return result


def _persisted_reference(content: str) -> Path | None:
    if content.startswith("[truncated: ") and content.endswith("]") and "\n" not in content:
        return Path(content[len("[truncated: ") : -1])
    prefix = "[tool output persisted]\nFull output saved to workspace path: "
    if content.startswith(prefix):
        return Path(content[len(prefix) :].split("\n", 1)[0])
    return None


def maybe_persist_tool_result(
    workspace: Path | None,
    session_key: str | None,
    tool_call_id: str,
    content: str,
    *,
    max_chars: int,
) -> str:
    """Offload oversized text.

    Complete references may exceed the per-block ``max_chars`` budget.
    """
    if workspace is None or max_chars <= 0 or len(content) <= max_chars:
        return content

    reference = _persisted_reference(content)
    if reference is not None and reference.is_file():
        return content

    root = ensure_dir(workspace / _TOOL_RESULTS_DIR)
    bucket = ensure_dir(root / safe_filename(session_key or "default"))
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    path = bucket / f"{safe_filename(tool_call_id)}-{digest}.txt"
    if not path.exists():
        _atomic_write_text(path, content)

    reference_path = str(path.resolve())
    overhead = len(
        _render_tool_result_reference(
            reference_path,
            original_size=len(content),
            preview="",
            truncated_preview=True,
        )
    )
    available = max(0, max_chars - overhead)
    separator = "\n...\n"
    tail_chars = min(1200, max(0, (available - len(separator)) // 4))
    if tail_chars:
        head_chars = available - tail_chars - len(separator)
        preview = content[:head_chars] + separator + content[-tail_chars:]
    else:
        preview = content[:available]
    return _render_tool_result_reference(
        reference_path,
        original_size=len(content),
        preview=preview,
        truncated_preview=True,
        max_chars=max_chars,
    )
