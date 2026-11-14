"""Parse complete Chat Completions responses."""

from typing import Any, cast

from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.catalog.contracts import ProviderSpec
from cirno_core.providers.tool_calls import ToolCallRequest, parse_tool_arguments

from .text import extract_text, extract_thinking
from .tools import extract_text_tool_calls, extract_tool_extras, short_tool_id
from .usage import extract_usage
from .wire import mapping


def parse_response(response: Any, *, spec: ProviderSpec | None = None) -> LLMResponse:
    if isinstance(response, str):
        return LLMResponse(content=response, finish_reason="stop")

    response_map = mapping(response)
    if response_map is None:
        raise TypeError(f"Unsupported chat response type: {type(response).__name__}")
    choices = cast(
        list[object],
        response_map.get("choices") or [],
    )
    if not choices:
        content = extract_text(response_map.get("content") or response_map.get("output_text"))
        reasoning_content = extract_text(response_map.get("reasoning_content"))
        if content is not None:
            return LLMResponse(
                content=content,
                reasoning_content=reasoning_content,
                finish_reason=str(response_map.get("finish_reason") or "stop"),
                usage=extract_usage(response_map),
            )
        return LLMResponse(
            content="Error: API returned empty choices.",
            finish_reason="error",
            error_kind="empty",
        )

    choice0 = mapping(choices[0]) or {}
    msg0 = mapping(choice0.get("message")) or {}
    content = extract_text(msg0.get("content"))
    finish_reason = str(choice0.get("finish_reason") or "stop")

    raw_tool_calls: list[object] = []
    # StepFun: fallback to reasoning field when content is empty
    if not content and msg0.get("reasoning") and spec and spec.reasoning_as_content:
        content = extract_text(msg0.get("reasoning"))
    reasoning_content = msg0.get("reasoning_content")
    if reasoning_content is None and msg0.get("reasoning"):
        reasoning_content = extract_text(msg0.get("reasoning"))
    # Mistral reasoning models return thinking text inside the content
    # array; lift it into reasoning_content so the runner records it
    # under the reasoning trace.
    if reasoning_content is None and getattr(spec, "extract_thinking_blocks", False):
        reasoning_content = extract_thinking(msg0.get("content"))
    # Choices are alternative answers, not sequential steps. Match the stream
    # parser's selected choice instead of executing every alternative's tools.
    message_tool_calls = cast(object, msg0.get("tool_calls"))
    if isinstance(message_tool_calls, list):
        raw_tool_calls.extend(cast(list[object], message_tool_calls))

    # Deduplicate tool call IDs (same pattern as streaming path)
    # Some providers reuse the same ID for parallel tool calls.
    _seen_tc_ids: set[str] = set()
    parsed_tool_calls: list[ToolCallRequest] = []
    for tc in raw_tool_calls:
        tc_map = mapping(tc) or {}
        fn = mapping(tc_map.get("function")) or {}
        args = parse_tool_arguments(fn.get("arguments", {}))
        ec, prov, fn_prov = extract_tool_extras(tc)
        raw_id = str(tc_map.get("id") or short_tool_id())
        if not raw_id or raw_id in _seen_tc_ids:
            raw_id = short_tool_id()
        _seen_tc_ids.add(raw_id)
        parsed_tool_calls.append(
            ToolCallRequest(
                id=raw_id,
                name=str(fn.get("name") or ""),
                arguments=args,
                extra_content=ec,
                provider_specific_fields=prov,
                function_provider_specific_fields=fn_prov,
            )
        )
    if not parsed_tool_calls:
        content, parsed_tool_calls = extract_text_tool_calls(content)

    return LLMResponse(
        content=content,
        tool_calls=parsed_tool_calls,
        finish_reason=finish_reason,
        usage=extract_usage(response_map),
        reasoning_content=reasoning_content if isinstance(reasoning_content, str) else None,
    )
