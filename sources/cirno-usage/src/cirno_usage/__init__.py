"""Public LLM usage records and persistence services."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cirno_usage.models import LLMCallRecord
    from cirno_usage.service import (
        get_llm_usage_store,
        llm_usage_payload,
        record_llm_call,
    )
    from cirno_usage.store import LLMUsageStore

_EXPORTS = {
    "LLMCallRecord": "cirno_usage.models",
    "LLMUsageStore": "cirno_usage.store",
    "get_llm_usage_store": "cirno_usage.service",
    "record_llm_call": "cirno_usage.service",
    "llm_usage_payload": "cirno_usage.service",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))


__all__ = [
    "LLMCallRecord",
    "LLMUsageStore",
    "get_llm_usage_store",
    "record_llm_call",
    "llm_usage_payload",
]
