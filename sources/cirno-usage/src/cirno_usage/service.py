"""Unified, content-free LLM usage backend."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from cirno_usage.models import LLMCallRecord
from cirno_usage.store import LLMUsageStore

_STORES_LOCK = threading.Lock()
_STORES: dict[Path, LLMUsageStore] = {}


def get_llm_usage_store(path: Path) -> LLMUsageStore:
    resolved = path.resolve(strict=False)
    with _STORES_LOCK:
        store = _STORES.get(resolved)
        if store is None:
            store = LLMUsageStore(resolved)
            _STORES[resolved] = store
        return store


def record_llm_call(call: LLMCallRecord, *, path: Path) -> None:
    """Record a content-free physical model call in the selected instance."""
    get_llm_usage_store(path).record(call)


def llm_usage_payload(
    path: Path,
    *,
    days: int = 371,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    return get_llm_usage_store(path).usage_payload(
        days=days,
        timezone_name=timezone_name,
    )
