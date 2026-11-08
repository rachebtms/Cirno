"""Classify provider failures and parse retry timing independently of transports."""

from __future__ import annotations

import json
import math
import re
from contextlib import suppress
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, cast

from cirno_core.providers.contracts import LLMResponse

TRANSIENT_ERROR_MARKERS = (
    "429",
    "rate limit",
    "500",
    "502",
    "503",
    "504",
    "overloaded",
    "timeout",
    "timed out",
    "connection",
    "server error",
    "server_error",
    "temporarily unavailable",
    "速率限制",
    "访问量过大",
)

RETRYABLE_STATUS_CODES = frozenset({408, 409, 429})

TRANSIENT_ERROR_KINDS = frozenset({"timeout", "connection"})

NON_RETRYABLE_429_ERROR_TOKENS = frozenset(
    {
        "insufficient_quota",
        "quota_exceeded",
        "quota_exhausted",
        "billing_hard_limit_reached",
        "insufficient_balance",
        "insufficient_credits",
        "credit_balance_too_low",
        "billing_not_active",
        "payment_required",
    }
)

RETRYABLE_429_ERROR_TOKENS = frozenset(
    {
        "rate_limit_exceeded",
        "rate_limit_error",
        "too_many_requests",
        "request_limit_exceeded",
        "requests_limit_exceeded",
        "overloaded_error",
    }
)

NON_RETRYABLE_429_TEXT_MARKERS = (
    "insufficient_quota",
    "insufficient quota",
    "quota exceeded",
    "quota exhausted",
    "billing hard limit",
    "billing_hard_limit_reached",
    "billing not active",
    "insufficient balance",
    "insufficient_balance",
    "insufficient credits",
    "insufficient_credits",
    "credit balance too low",
    "payment required",
    "out of credits",
    "out of quota",
    "exceeded your current quota",
)

RETRYABLE_429_TEXT_MARKERS = (
    "rate limit",
    "rate_limit",
    "too many requests",
    "retry after",
    "try again in",
    "temporarily unavailable",
    "overloaded",
    "concurrency limit",
    "速率限制",
)


def response_from_exception(exc: Exception) -> LLMResponse:
    """Convert an unexpected exception while retaining retry metadata."""
    error_names = tuple(cls.__name__.lower() for cls in type(exc).__mro__)
    error_kind: str | None = None
    error_should_retry: bool | None = None
    if any("timeout" in name for name in error_names):
        error_kind = "timeout"
        error_should_retry = True
    elif any(
        token in name
        for name in error_names
        for token in ("connect", "connection", "network", "protocol", "transport")
    ):
        error_kind = "connection"
        error_should_retry = True
    elif any("ratelimit" in name or "throttl" in name for name in error_names):
        error_kind = "rate_limit"
        error_should_retry = True
    elif any("server" in name or "internal" in name for name in error_names):
        error_kind = "server_error"
        error_should_retry = True
    elif any(
        token in name
        for name in error_names
        for token in ("auth", "credential", "permissiondenied", "unauthor")
    ):
        error_kind = "authentication"

    response = getattr(exc, "response", None)
    raw_status = getattr(exc, "status_code", None)
    if raw_status is None and response is not None:
        raw_status = getattr(response, "status_code", None)
    try:
        error_status_code = int(raw_status) if raw_status is not None else None
    except (TypeError, ValueError):
        error_status_code = None

    raw_error_type = getattr(exc, "error_type", None)
    raw_error_code = getattr(exc, "error_code", None)
    detail = str(exc).strip() or type(exc).__name__
    return LLMResponse(
        content=f"Error calling LLM: {detail}",
        finish_reason="error",
        error_status_code=error_status_code,
        error_kind=error_kind,
        error_type=str(raw_error_type) if raw_error_type is not None else None,
        error_code=str(raw_error_code) if raw_error_code is not None else None,
        error_should_retry=error_should_retry,
    )


def is_transient_error(content: str | None) -> bool:
    err = (content or "").lower()
    return any(marker in err for marker in TRANSIENT_ERROR_MARKERS)


def is_transient_response(response: LLMResponse) -> bool:
    """Prefer structured error metadata, fallback to text markers for legacy providers."""
    if response.error_should_retry is not None:
        return bool(response.error_should_retry)

    if response.error_status_code is not None:
        status = int(response.error_status_code)
        if status == 429:
            return is_retryable_rate_limit(response)
        if status in RETRYABLE_STATUS_CODES or status >= 500:
            return True

    kind = (response.error_kind or "").strip().lower()
    if kind in TRANSIENT_ERROR_KINDS:
        return True

    return is_transient_error(response.content)


def is_billing_error(response: LLMResponse) -> bool:
    """Detect API-key arrearage / quota / billing errors that won't clear on retry.

    These surface as HTTP 402 or as billing semantic tokens (e.g.
    ``insufficient_quota``, ``payment_required``); reuses the same token and
    text markers the 429 retry policy treats as non-retryable.
    """
    if response.error_status_code is not None and int(response.error_status_code) == 402:
        return True

    type_token = normalize_error_token(response.error_type)
    code_token = normalize_error_token(response.error_code)
    if any(
        token in NON_RETRYABLE_429_ERROR_TOKENS
        for token in (type_token, code_token)
        if token is not None
    ):
        return True

    content = (response.content or "").lower()
    return any(marker in content for marker in NON_RETRYABLE_429_TEXT_MARKERS)


def normalize_error_token(value: Any) -> str | None:
    if value is None:
        return None
    token = str(value).strip().lower()
    return token or None


def extract_error_type_code(payload: Any) -> tuple[str | None, str | None]:
    data: dict[str, Any] | None = None
    if isinstance(payload, dict):
        data = cast(dict[str, Any], payload)
    elif isinstance(payload, str):
        text = payload.strip()
        if text:
            try:
                parsed = json.loads(text)
            except (json.JSONDecodeError, RecursionError):
                parsed = None
            if isinstance(parsed, dict):
                data = cast(dict[str, Any], parsed)
    if data is None:
        return None, None

    error_obj = data.get("error")
    type_value = data.get("type")
    code_value = data.get("code")
    error_object = cast(dict[str, Any], error_obj) if isinstance(error_obj, dict) else None
    if error_object is not None:
        type_value = error_object.get("type") or type_value
        code_value = error_object.get("code") or code_value

    return normalize_error_token(type_value), normalize_error_token(code_value)


def is_retryable_rate_limit(response: LLMResponse) -> bool:
    type_token = normalize_error_token(response.error_type)
    code_token = normalize_error_token(response.error_code)
    semantic_tokens = {token for token in (type_token, code_token) if token is not None}
    if any(token in NON_RETRYABLE_429_ERROR_TOKENS for token in semantic_tokens):
        return False

    content = (response.content or "").lower()
    if any(marker in content for marker in NON_RETRYABLE_429_TEXT_MARKERS):
        return False

    if any(token in RETRYABLE_429_ERROR_TOKENS for token in semantic_tokens):
        return True
    if any(marker in content for marker in RETRYABLE_429_TEXT_MARKERS):
        return True
    # Unknown 429 defaults to WAIT+retry.
    return True


def retry_after_text(content: str | None) -> float | None:
    text = (content or "").lower()
    patterns = (
        r"retry after\s+(\d+(?:\.\d+)?)\s*(ms|milliseconds|s|sec|secs|seconds|m|min|minutes)?",
        r"try again in\s+(\d+(?:\.\d+)?)\s*(ms|milliseconds|s|sec|secs|seconds|m|min|minutes)",
        r"wait\s+(\d+(?:\.\d+)?)\s*(ms|milliseconds|s|sec|secs|seconds|m|min|minutes)\s*before retry",
        r"retry[_-]?after[\"'\s:=]+(\d+(?:\.\d+)?)",
    )
    for idx, pattern in enumerate(patterns):
        if idx == 1 and (compound := compound_retry_delay(text)) is not None:
            return compound
        match = re.search(pattern, text)
        if not match:
            continue
        value = float(match.group(1))
        unit = match.group(2) if idx < 3 else "s"
        return retry_seconds(value, unit)
    return None


def compound_retry_delay(text: str) -> float | None:
    """Sum Go-style durations such as OpenAI's ``try again in 1m30s``."""
    match = re.search(r"try again in\s+((?:\d+(?:\.\d+)?(?:ms|h|m|s))+)(?![a-z])", text)
    if not match:
        return None
    unit_seconds = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
    parts = re.findall(r"(\d+(?:\.\d+)?)(ms|h|m|s)", match.group(1))
    duration = sum(float(value) * unit_seconds[unit] for value, unit in parts)
    return max(0.1, duration) if math.isfinite(duration) else None


def retry_seconds(value: float, unit: str | None = None) -> float | None:
    normalized_unit = (unit or "s").lower()
    if normalized_unit in {"ms", "milliseconds"}:
        value /= 1000.0
    elif normalized_unit in {"m", "min", "minutes"}:
        value *= 60.0
    return max(0.1, value) if math.isfinite(value) else None


def retry_after_headers(headers: Any) -> float | None:
    if not headers:
        return None

    def _header_value(name: str) -> Any:
        if hasattr(headers, "get"):
            value = headers.get(name) or headers.get(name.title())
            if value is not None:
                return value
        if isinstance(headers, dict):
            for key, value in cast(dict[object, Any], headers).items():
                if isinstance(key, str) and key.lower() == name.lower():
                    return value
        return None

    with suppress(TypeError, ValueError):
        retry_ms = _header_value("retry-after-ms")
        if retry_ms is not None:
            value = float(retry_ms) / 1000.0
            if value > 0 and math.isfinite(value):
                return value

    retry_after = _header_value("retry-after")
    if retry_after is None:
        return None
    retry_after_text = str(retry_after).strip()
    if not retry_after_text:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", retry_after_text):
        return retry_seconds(float(retry_after_text), "s")
    try:
        retry_at = parsedate_to_datetime(retry_after_text)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    remaining = (retry_at - datetime.now(retry_at.tzinfo)).total_seconds()
    return max(0.1, remaining)


def retry_after_response(response: LLMResponse) -> float | None:
    if (
        response.error_retry_after_s is not None
        and response.error_retry_after_s > 0
        and math.isfinite(response.error_retry_after_s)
    ):
        return response.error_retry_after_s
    if (
        response.retry_after is not None
        and response.retry_after > 0
        and math.isfinite(response.retry_after)
    ):
        return response.retry_after
    return retry_after_text(response.content)


def public_error_kind(response: LLMResponse) -> str:
    """Return a stable public category without exposing provider details."""
    if response.primary_error_kind is not None:
        return response.primary_error_kind
    if is_billing_error(response):
        return "billing"
    kind = (response.error_kind or "").strip().lower()
    # A plain 403 can be a policy or permission rejection, not bad credentials.
    if kind in {"authentication", "oauth_auth_required"} or response.error_status_code == 401:
        return "authentication"
    if kind in {"configuration", "connection", "timeout"}:
        return kind
    if response.error_status_code == 429:
        return "rate_limit"
    if response.error_status_code is not None and response.error_status_code >= 500:
        return "server"
    return "unknown"
