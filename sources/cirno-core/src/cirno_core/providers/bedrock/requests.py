"""Bedrock requests conversion."""

from __future__ import annotations

from typing import Any, cast

from cirno_core.providers.bedrock.messages import (
    contains_tool_blocks,
    convert_messages,
    convert_tool_choice,
    convert_tools,
    noop_tool,
)
from cirno_core.providers.messages import sanitize_empty_content

_TEMPERATURE_UNSUPPORTED_MODEL_TOKENS = ("claude-opus-4-7",)
_ADAPTIVE_THINKING_ONLY_MODEL_TOKENS = ("claude-opus-4-7",)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(
                cast(dict[str, Any], merged[key]),
                cast(dict[str, Any], value),
            )
        else:
            merged[key] = value
    return merged


def strip_prefix(model: str) -> str:
    if model.startswith("bedrock/"):
        return model[len("bedrock/") :]
    return model


def matches_model_token(model: str, tokens: tuple[str, ...]) -> bool:
    model_lower = model.lower()
    return any(token in model_lower for token in tokens)


def supports_temperature(model: str) -> bool:
    return not matches_model_token(model, _TEMPERATURE_UNSUPPORTED_MODEL_TOKENS)


def uses_adaptive_thinking_only(model: str) -> bool:
    return matches_model_token(model, _ADAPTIVE_THINKING_ONLY_MODEL_TOKENS)


def adaptive_thinking(reasoning_effort: str | None) -> dict[str, Any] | None:
    if not reasoning_effort:
        return None
    effort = reasoning_effort.lower()
    if effort == "none":
        return None
    thinking: dict[str, Any] = {"type": "adaptive"}
    if effort != "adaptive":
        thinking["effort"] = effort
    return thinking


def build_request(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    model: str | None,
    max_tokens: int,
    temperature: float,
    reasoning_effort: str | None,
    tool_choice: str | dict[str, Any] | None,
    *,
    default_model: str = "bedrock/global.anthropic.claude-opus-4-7",
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model_id = strip_prefix(model or default_model)
    system, bedrock_messages = convert_messages(sanitize_empty_content(messages))
    if not bedrock_messages:
        bedrock_messages = [{"role": "user", "content": [{"text": "(empty)"}]}]

    kwargs: dict[str, Any] = {
        "modelId": model_id,
        "messages": bedrock_messages,
        "inferenceConfig": {"maxTokens": max(1, max_tokens)},
    }
    if system:
        kwargs["system"] = system
    if supports_temperature(model_id):
        kwargs["inferenceConfig"]["temperature"] = temperature

    additional: dict[str, Any] = {}
    if uses_adaptive_thinking_only(model_id):
        thinking = adaptive_thinking(reasoning_effort)
        if thinking:
            additional["thinking"] = thinking
    if extra_body:
        additional = _deep_merge(additional, extra_body)
    if additional:
        kwargs["additionalModelRequestFields"] = additional

    bedrock_tools = convert_tools(tools)
    tool_config: dict[str, Any] | None = None
    if bedrock_tools:
        tool_config = {"tools": bedrock_tools}
        choice = convert_tool_choice(tool_choice)
        if choice:
            tool_config["toolChoice"] = choice
    elif contains_tool_blocks(bedrock_messages):
        tool_config = {"tools": [noop_tool()]}

    if tool_config:
        kwargs["toolConfig"] = tool_config

    return kwargs
