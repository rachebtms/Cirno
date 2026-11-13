"""
cirno - A lightweight AI agent framework
"""

import tomllib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cirno_core.agent.tools.context import RequestContext
    from cirno_core.bus.runtime_events import SessionTurnPersisted
    from cirno_core.sdk.assistant import (
        STREAM_EVENT_REASONING_COMPLETED,
        STREAM_EVENT_REASONING_DELTA,
        STREAM_EVENT_RUN_COMPLETED,
        STREAM_EVENT_RUN_FAILED,
        STREAM_EVENT_RUN_STARTED,
        STREAM_EVENT_TEXT_COMPLETED,
        STREAM_EVENT_TEXT_DELTA,
        STREAM_EVENT_TOOL_COMPLETED,
        STREAM_EVENT_TOOL_FAILED,
        STREAM_EVENT_TOOL_STARTED,
        STREAM_EVENT_TYPES,
        Cirno,
        LLMUsage,
        RunResult,
        RunStream,
        SessionInfo,
        SessionSnapshot,
        StreamEvent,
        StreamEventType,
    )
    from cirno_core.runtime.context import RuntimeContextBlock, RuntimeContextProvider


def _read_pyproject_version() -> str | None:
    """Read the source-tree version when package metadata is unavailable."""
    pyproject = Path(__file__).resolve().parents[4] / "pyproject.toml"
    if not pyproject.exists():
        return None
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return data.get("project", {}).get("version")


def _resolve_version() -> str:
    try:
        return _pkg_version("cirno-ai")
    except PackageNotFoundError:
        # Source checkouts often import cirno without installed dist-info.
        return _read_pyproject_version() or "0.2.14"


__version__ = _resolve_version()
__logo__ = "❄️"

_LAZY_EXPORTS = {
    "Cirno": "cirno_core.sdk.assistant",
    "LLMUsage": "cirno_usage.types",
    "RunStream": "cirno_core.sdk.assistant",
    "RunResult": "cirno_core.sdk.assistant",
    "RequestContext": "cirno_core.agent.tools.context",
    "RuntimeContextBlock": "cirno_core.runtime.context",
    "RuntimeContextProvider": "cirno_core.runtime.context",
    "SessionInfo": "cirno_core.sdk.assistant",
    "SessionSnapshot": "cirno_core.sdk.assistant",
    "STREAM_EVENT_REASONING_COMPLETED": "cirno_core.sdk.assistant",
    "STREAM_EVENT_REASONING_DELTA": "cirno_core.sdk.assistant",
    "STREAM_EVENT_RUN_COMPLETED": "cirno_core.sdk.assistant",
    "STREAM_EVENT_RUN_FAILED": "cirno_core.sdk.assistant",
    "STREAM_EVENT_RUN_STARTED": "cirno_core.sdk.assistant",
    "STREAM_EVENT_TEXT_COMPLETED": "cirno_core.sdk.assistant",
    "STREAM_EVENT_TEXT_DELTA": "cirno_core.sdk.assistant",
    "STREAM_EVENT_TOOL_COMPLETED": "cirno_core.sdk.assistant",
    "STREAM_EVENT_TOOL_FAILED": "cirno_core.sdk.assistant",
    "STREAM_EVENT_TOOL_STARTED": "cirno_core.sdk.assistant",
    "STREAM_EVENT_TYPES": "cirno_core.sdk.assistant",
    "StreamEvent": "cirno_core.sdk.assistant",
    "StreamEventType": "cirno_core.sdk.assistant",
    "SessionTurnPersisted": "cirno_core.bus.runtime_events",
}


def __getattr__(name: str) -> Any:
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module
    mod = import_module(module_path, __name__)
    val = getattr(mod, name)
    globals()[name] = val
    return val


__all__ = [
    "Cirno",
    "LLMUsage",
    "RunResult",
    "RequestContext",
    "RuntimeContextBlock",
    "RuntimeContextProvider",
    "RunStream",
    "SessionInfo",
    "SessionSnapshot",
    "STREAM_EVENT_REASONING_COMPLETED",
    "STREAM_EVENT_REASONING_DELTA",
    "STREAM_EVENT_RUN_COMPLETED",
    "STREAM_EVENT_RUN_FAILED",
    "STREAM_EVENT_RUN_STARTED",
    "STREAM_EVENT_TEXT_COMPLETED",
    "STREAM_EVENT_TEXT_DELTA",
    "STREAM_EVENT_TOOL_COMPLETED",
    "STREAM_EVENT_TOOL_FAILED",
    "STREAM_EVENT_TOOL_STARTED",
    "STREAM_EVENT_TYPES",
    "StreamEvent",
    "StreamEventType",
    "SessionTurnPersisted",
]
