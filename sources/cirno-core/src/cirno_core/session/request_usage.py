"""Small, content-free request snapshots available before a turn finishes."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from cirno_usage.types import LLMUsage

RECENT_REQUEST_USAGE_KEY = "_recent_request_usage"
MAX_RECENT_REQUESTS = 8


def append_request_usage(metadata: dict[str, Any], usage: LLMUsage) -> None:
    """Keep completed model responses independently of paginated chat history."""
    recent = list(metadata.get(RECENT_REQUEST_USAGE_KEY, []))
    recent.append({
        "id": str(uuid4()),
        "timestamp": time.time_ns() // 1_000_000,
        "usage": usage.to_turn_dict(),
    })
    metadata[RECENT_REQUEST_USAGE_KEY] = recent[-MAX_RECENT_REQUESTS:]
