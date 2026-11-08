"""Measure request pressure and fit only unsent recoverable file reads."""

from __future__ import annotations

from typing import Any

from cirno_core.agent.governance.contracts import (
    ContextGovernanceConfig,
    ContextWindowExceededError,
)
from cirno_core.agent.tools.naming import implementation_name
from cirno_core.providers.base import CONTEXT_SAFETY_BUFFER
from cirno_core.utils.token_estimation import estimate_prompt_tokens_chain
from cirno_usage.types import LLMUsage


def request_extends_measured(
    measured: list[dict[str, Any]],
    current: list[dict[str, Any]],
) -> bool:
    """Return whether measured messages are an unchanged prefix of the request."""
    return len(current) >= len(measured) and all(
        current[index] == measured[index] for index in range(len(measured))
    )


def input_budget(config: ContextGovernanceConfig) -> int:
    if not config.context_window_tokens:
        return 0

    provider_max_tokens = getattr(
        getattr(config.provider, "generation", None),
        "max_tokens",
        4096,
    )
    max_output = (
        config.max_tokens
        if isinstance(config.max_tokens, int)
        else (provider_max_tokens if isinstance(provider_max_tokens, int) else 4096)
    )
    budget = min(
        config.context_window_tokens - max_output - CONTEXT_SAFETY_BUFFER,
        int(config.context_window_tokens * config.active_compact_percent / 100),
    )
    return budget if budget > 0 else 0


def ensure_request_fits(
    config: ContextGovernanceConfig,
    messages: list[dict[str, Any]],
    *,
    tool_definitions: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Validate an exact model request without dropping any messages."""
    if not config.context_window_tokens:
        return messages
    budget = input_budget(config)
    estimated, source = estimate_prompt_tokens_chain(
        config.provider,
        config.model,
        messages,
        tool_definitions,
    )
    if budget > 0 and estimated <= budget:
        return messages
    raise ContextWindowExceededError(
        session_key=config.session_key,
        estimated_tokens=estimated,
        input_budget=budget,
        source=source,
    )


def request_pressure(
    config: ContextGovernanceConfig,
    messages: list[dict[str, Any]],
    usage: LLMUsage | None,
    *,
    usage_matches_messages: bool,
    usage_prefixes_messages: bool,
    tool_definitions: list[dict[str, Any]] | None,
    request_context_tokens: int | None = None,
    minimum_percent: int = 100,
) -> tuple[int, str] | None:
    """Return the authoritative measurement when a request is pressured."""
    if not config.context_window_tokens:
        return None
    budget = input_budget(config)
    if request_context_tokens is not None:
        measured = request_context_tokens
        source = "resumed provider state plus pending messages"
    elif usage_matches_messages and usage is not None and usage.context_tokens is not None:
        measured = usage.context_tokens
        source = "matching provider usage"
    else:
        measured, source = estimate_prompt_tokens_chain(
            config.provider,
            config.model,
            messages,
            tool_definitions,
        )
        if (
            usage_prefixes_messages
            and usage is not None
            and usage.reported_tokens > 0
            and usage.context_tokens is not None
            and usage.context_tokens > measured
        ):
            measured = usage.context_tokens
            source = "prior provider usage plus pending messages"
    if budget > 0 and measured < budget * minimum_percent / 100:
        return None
    return measured, source


def fit_pending_file_reads(
    config: ContextGovernanceConfig,
    messages: list[dict[str, Any]],
    delta_messages: list[dict[str, Any]],
    *,
    tool_definitions: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Make oversized, unread file results recoverable after history compaction."""
    notice = (
        "Error: read_file result was not sent because the combined request exceeds "
        "the context budget. No file was modified by this recovery. Read one file at a time "
        "with a smaller offset/limit range; for large single-line JSON, use exec "
        "to select only the needed records or fields."
    )
    pending_ids = {
        message.get("tool_call_id")
        for message in delta_messages
        if message.get("role") == "tool"
        and implementation_name(message.get("name", "")) == "read_file"
        and isinstance(message.get("tool_call_id"), str)
    }
    candidates = iter(
        sorted(
            (
                index
                for index, message in enumerate(messages)
                if message.get("role") == "tool"
                and message.get("tool_call_id") in pending_ids
                and isinstance(message.get("content"), str)
                and len(message["content"].encode("utf-8")) > len(notice)
            ),
            key=lambda index: len(messages[index]["content"].encode("utf-8")),
            reverse=True,
        )
    )
    prepared = list(messages)
    replacements: dict[str, str] = {}
    while True:
        try:
            fitted = ensure_request_fits(
                config,
                prepared,
                tool_definitions=tool_definitions,
            )
            return fitted, replacements
        except ContextWindowExceededError:
            index = next(candidates, None)
            if index is None:
                raise
            # Only unread results can change. Record the same text for replay,
            # so a later turn does not restore content the model never received.
            replacements[prepared[index]["tool_call_id"]] = notice
            prepared[index] = {**prepared[index], "content": notice}
