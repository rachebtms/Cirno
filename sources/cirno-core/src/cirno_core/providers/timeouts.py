"""Model connection, response and stream inactivity timeouts."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

import httpx
from loguru import logger

STREAM_IDLE_TIMEOUT_ENV = "CIRNO_STREAM_IDLE_TIMEOUT_S"
DEFAULT_STREAM_IDLE_TIMEOUT_S = 90.0
MAX_STREAM_IDLE_TIMEOUT_S = 3600.0


def resolve_stream_idle_timeout_s(
    *,
    env_value: str | None = None,
    default: float = DEFAULT_STREAM_IDLE_TIMEOUT_S,
    maximum: float = MAX_STREAM_IDLE_TIMEOUT_S,
) -> float:
    """Return a safe streaming idle timeout from env/config text."""
    raw = os.environ.get(STREAM_IDLE_TIMEOUT_ENV) if env_value is None else env_value
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning("Ignoring invalid {}={!r}; using {}", STREAM_IDLE_TIMEOUT_ENV, raw, default)
        return default
    if not math.isfinite(value) or value <= 0:
        logger.warning(
            "Ignoring invalid timeout {}={!r}; using {}", STREAM_IDLE_TIMEOUT_ENV, raw, default
        )
        return default
    if value > maximum:
        logger.warning("Clamping {}={!r} to {}", STREAM_IDLE_TIMEOUT_ENV, raw, maximum)
        return maximum
    return value



@dataclass(slots=True)
class ProviderTimeouts:
    request_s: float = 120.0
    stream_idle_s: float = field(default_factory=resolve_stream_idle_timeout_s)

    def httpx(self, *, stream: bool = False) -> httpx.Timeout:
        return httpx.Timeout(self.request_s, read=self.stream_idle_s if stream else self.request_s)
