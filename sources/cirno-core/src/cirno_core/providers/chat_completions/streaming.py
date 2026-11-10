"""Incremental Chat Completions parsing without retaining SDK chunks."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import StringIO
from typing import Any, cast

from cirno_usage.types import LLMUsage
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.tool_calls import ToolCallRequest, parse_tool_arguments

from .text import extract_text, extract_thinking
from .tools import extract_text_tool_calls, extract_tool_extras, short_tool_id
from .usage import extract_usage
from .wire import field as wire_field
from .wire import mapping


@dataclass
class StreamDelta:
    content: str | None = None
    reasoning: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _ToolBuffer:
    id: str = ""
    name: str = ""
    arguments: StringIO = field(default_factory=StringIO)
    extra_content: dict[str, Any] | None = None
    provider_fields: dict[str, Any] | None = None
    function_fields: dict[str, Any] | None = None


class ChatStreamAccumulator:
    def __init__(self) -> None:
        self._content = StringIO()
        self._reasoning = StringIO()
        self._tools: dict[int, _ToolBuffer] = {}
        self._finish_reason = "stop"
        self._usage: LLMUsage | None = None
        self.completed = False

    def _tool_index(self, index: int | None, identity: str | None, fallback: int) -> int:
        if index is not None:
            return index
        if not identity:
            if fallback or not self._tools:
                return fallback
            if len(self._tools) == 1:
                return next(iter(self._tools))
            raise ValueError("Tool-call delta is missing both index and ID for multiple calls")
        # Compatible gateways may omit index while identifying every delta by ID.
        # Keep those calls separate even when each chunk contains just one call.
        matches = [slot for slot, buffer in self._tools.items() if buffer.id == identity]
        if len(matches) > 1:
            raise ValueError("Tool-call delta has an ambiguous ID and no index")
        if matches:
            return matches[0]
        existing = self._tools.get(fallback)
        if existing is None or not existing.id:
            return fallback
        return max(self._tools) + 1

    def _tool_delta(
        self, value: object, fallback_index: int, *, legacy: bool = False
    ) -> dict[str, Any]:
        index = wire_field(value, "index") if not legacy else 0
        identity = wire_field(value, "id") if not legacy else None
        index = self._tool_index(index, identity, fallback_index)
        buffer = self._tools.setdefault(index, _ToolBuffer())
        function = value if legacy else wire_field(value, "function")
        name = wire_field(function, "name") if function is not None else None
        arguments = wire_field(function, "arguments") if function is not None else None
        if identity:
            buffer.id = str(identity)
        if name:
            buffer.name = str(name)
        if arguments:
            buffer.arguments.write(str(arguments))
        if not legacy:
            extras, provider_fields, function_fields = extract_tool_extras(value)
            if extras:
                buffer.extra_content = extras
            if provider_fields:
                buffer.provider_fields = provider_fields
            if function_fields:
                buffer.function_fields = function_fields
        return {
            "index": index,
            "call_id": str(identity or ""),
            "name": str(name or ""),
            "arguments_delta": str(arguments or ""),
        }

    def consume(self, chunk: object) -> StreamDelta:
        if isinstance(chunk, str):
            self._content.write(chunk)
            return StreamDelta(content=chunk)
        chunk_map = mapping(chunk)
        if chunk_map is None:
            raise TypeError(f"Unsupported chat chunk type: {type(chunk).__name__}")
        self._usage = extract_usage(chunk_map) or self._usage
        choices = cast(list[object], chunk_map.get("choices") or [])
        if not choices:
            content = extract_text(chunk_map.get("content") or chunk_map.get("output_text"))
            if content:
                self._content.write(content)
            return StreamDelta(content=content)
        choice = mapping(choices[0]) or {}
        if choice.get("finish_reason"):
            self._finish_reason = str(choice["finish_reason"])
            self.completed = True
        delta = mapping(choice.get("delta")) or {}
        raw_content = delta.get("content")
        content = extract_text(raw_content)
        reasoning = (
            extract_text(delta.get("reasoning_content"))
            or extract_text(delta.get("reasoning"))
            or extract_thinking(raw_content)
        )
        if content:
            self._content.write(content)
        if reasoning:
            self._reasoning.write(reasoning)
        calls = [
            self._tool_delta(value, index)
            for index, value in enumerate(cast(list[object], delta.get("tool_calls") or []))
        ]
        if delta.get("function_call"):
            calls.append(self._tool_delta(delta["function_call"], 0, legacy=True))
        return StreamDelta(content=content, reasoning=reasoning, tool_calls=calls)

    def response(self) -> LLMResponse:
        seen_ids: set[str] = set()
        calls: list[ToolCallRequest] = []
        for buffer in self._tools.values():
            identity = buffer.id
            if not identity or identity in seen_ids:
                identity = short_tool_id()
            seen_ids.add(identity)
            calls.append(
                ToolCallRequest(
                    id=identity,
                    name=buffer.name,
                    arguments=parse_tool_arguments(buffer.arguments.getvalue()),
                    extra_content=buffer.extra_content,
                    provider_specific_fields=buffer.provider_fields,
                    function_provider_specific_fields=buffer.function_fields,
                )
            )
        content = self._content.getvalue() or None
        if not calls:
            content, calls = extract_text_tool_calls(content)
        return LLMResponse(
            content=content,
            reasoning_content=self._reasoning.getvalue() or None,
            tool_calls=calls,
            finish_reason=self._finish_reason,
            usage=self._usage,
        )
