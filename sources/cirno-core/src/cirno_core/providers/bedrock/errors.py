"""Bedrock errors conversion."""

from __future__ import annotations

from typing import Any, cast

from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.errors import retry_after_headers, retry_after_text


def handle_error(e: Exception) -> LLMResponse:
    response_value = getattr(e, "response", None)
    response = cast(dict[str, Any], response_value) if isinstance(response_value, dict) else {}
    metadata_value = response.get("ResponseMetadata", {})
    metadata = cast(dict[str, Any], metadata_value) if isinstance(metadata_value, dict) else {}
    headers = metadata.get("HTTPHeaders")
    error_value = response.get("Error", {})
    error_obj = cast(dict[str, Any], error_value) if isinstance(error_value, dict) else {}
    message = error_obj.get("Message")
    code = error_obj.get("Code")
    status_code = metadata.get("HTTPStatusCode")
    body = cast(str, message or str(e))
    retry_after = retry_after_headers(headers)
    if retry_after is None:
        retry_after = retry_after_text(body)

    error_name = e.__class__.__name__.lower()
    error_kind = None
    if "timeout" in error_name:
        error_kind = "timeout"
    elif "connection" in error_name or "endpoint" in error_name:
        error_kind = "connection"

    code_text = str(code or "").lower()
    should_retry = None
    if status_code is not None:
        should_retry = int(status_code) == 429 or int(status_code) >= 500
    if any(token in code_text for token in ("throttl", "timeout", "unavailable", "modelnotready")):
        should_retry = True

    return LLMResponse(
        content=f"Error: {str(body).strip()[:500]}",
        finish_reason="error",
        retry_after=retry_after,
        error_status_code=int(status_code) if status_code is not None else None,
        error_kind=error_kind,
        error_type=code_text or None,
        error_code=code_text or None,
        error_retry_after_s=retry_after,
        error_should_retry=should_retry,
    )
