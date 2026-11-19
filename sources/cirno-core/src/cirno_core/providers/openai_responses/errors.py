"""Structured Responses failures without retaining upstream prompt echoes."""

from __future__ import annotations

import re
from typing import Any, cast

from cirno_usage.types import LLMUsage

from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.errors import (
    RETRYABLE_429_ERROR_TOKENS,
    RETRYABLE_STATUS_CODES,
    is_billing_error,
    is_transient_response,
    retry_after_headers,
    retry_after_text,
)


def _error_token(value: object) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9_.:/\[\]-]{1,160}", value):
        return value
    return None


class ResponsesAPIError(RuntimeError):
    """A failed response or event, projected through each owning adapter."""

    def __init__(self, event: dict[str, Any], *, usage: LLMUsage | None = None) -> None:
        self.usage = usage
        response = event.get("response")
        payload = cast(dict[str, Any], response) if isinstance(response, dict) else event
        error = payload.get("error")
        fields = cast(dict[str, Any], error) if isinstance(error, dict) else payload
        self.error_type = _error_token(fields.get("type"))
        if fields is payload and self.error_type in {"error", "response.failed"}:
            self.error_type = None
        self.error_code = (
            _error_token(error) if isinstance(error, str) else _error_token(fields.get("code"))
        )
        self.status_code = next(
            (
                value
                for value in (
                    event.get("status"),
                    event.get("status_code"),
                    payload.get("status_code"),
                    fields.get("status_code"),
                )
                if type(value) is int and 400 <= value <= 599
            ),
            None,
        )
        message = fields.get("message")
        if isinstance(error, str) and self.error_code is None:
            message = error
        compatibility_text = " ".join(
            value.lower()
            for value in (message, self.error_code, fields.get("param"))
            if isinstance(value, str)
        )
        self.api_unsupported = self.status_code in {400, 404, 422} and any(
            marker in compatibility_text
            for marker in (
                "responses",
                "response api",
                "max_output_tokens",
                "instructions",
                "previous_response",
                "unsupported",
                "not supported",
                "unknown parameter",
                "unrecognized request argument",
            )
        )
        self.compaction_unsupported = self.status_code in {400, 404, 422} and any(
            marker in compatibility_text
            for marker in (
                "context_management",
                "compact_threshold",
                "compaction_trigger",
            )
        )
        headers = event.get("headers") or payload.get("headers") or fields.get("headers")
        self.retry_after = retry_after_headers(headers)
        if self.retry_after is None and isinstance(message, str):
            self.retry_after = retry_after_text(message)

        # Interpret text for legacy retry hints locally; never store it on the error.
        diagnostic = LLMResponse(
            content=message if isinstance(message, str) else None,
            finish_reason="error",
            error_status_code=self.status_code,
            error_type=self.error_type,
            error_code=self.error_code,
        )
        tokens = {value.lower() for value in (self.error_type, self.error_code) if value}
        if is_billing_error(diagnostic):
            self.error_kind = "billing"
            self.should_retry = False
        elif self.status_code == 401 or tokens & {
            "authentication_error",
            "invalid_api_key",
            "invalid_token",
        }:
            self.error_kind = "authentication"
            self.should_retry = False
        elif self.status_code == 429 or tokens & RETRYABLE_429_ERROR_TOKENS:
            self.error_kind = "rate_limit"
            self.should_retry = True
        elif (
            self.status_code is not None
            and self.status_code >= 500
            or tokens & {"server_error", "internal_server_error"}
        ):
            self.error_kind = "server_error"
            self.should_retry = True
        else:
            self.error_kind = "http" if self.status_code is not None else "provider"
            self.should_retry = (
                self.status_code in RETRYABLE_STATUS_CODES
                if self.status_code is not None
                else is_transient_response(diagnostic)
            )
        detail = self.error_code or self.error_type
        super().__init__("Response failed" + (f" ({detail})" if detail else ""))

    def to_response(self) -> LLMResponse:
        return LLMResponse(
            content=str(self),
            finish_reason="error",
            retry_after=self.retry_after,
            usage=self.usage,
            error_status_code=self.status_code,
            error_kind=self.error_kind,
            error_type=self.error_type,
            error_code=self.error_code,
            error_retry_after_s=self.retry_after,
            error_should_retry=self.should_retry,
        )
