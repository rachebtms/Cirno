"""Tool calls and provider history argument serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast


def valid_tool_name(name: object) -> bool:
    """Use the same name check for newly generated calls and saved history."""
    return isinstance(name, str) and bool(name.strip())


@dataclass
class ToolCallRequest:
    """A tool call request from the LLM."""

    id: str
    name: str
    arguments: Any
    extra_content: dict[str, Any] | None = None
    provider_specific_fields: dict[str, Any] | None = None
    function_provider_specific_fields: dict[str, Any] | None = None

    def has_valid_name(self) -> bool:
        """Reject missing or blank names before execution and history replay."""
        return valid_tool_name(self.name)

    def to_openai_tool_call(self) -> dict[str, Any]:
        """Serialize to an OpenAI-style tool_call payload."""
        from cirno_vault.redaction import tool_arguments

        safe_arguments = tool_arguments(self.name, self.arguments)
        arguments = (
            safe_arguments
            if isinstance(safe_arguments, str)
            else json.dumps(safe_arguments, ensure_ascii=False)
        )
        tool_call: dict[str, Any] = {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": arguments,
            },
        }
        if self.extra_content:
            tool_call["extra_content"] = self.extra_content
        if self.provider_specific_fields:
            tool_call["provider_specific_fields"] = self.provider_specific_fields
        if self.function_provider_specific_fields:
            tool_call["function"]["provider_specific_fields"] = (
                self.function_provider_specific_fields
            )
        return tool_call


def parse_tool_arguments(arguments: Any) -> Any:
    """Parse provider tool arguments without guessing executable parameters.

    Valid JSON object strings become dicts. Empty strings become no-arg calls.
    Malformed JSON and JSON array/scalar values are preserved so ToolRegistry
    can reject them before execution.
    """
    if arguments is None:
        return {}
    if not isinstance(arguments, str):
        return arguments

    stripped = arguments.strip()
    if not stripped:
        return {}

    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, RecursionError):
        return arguments
    return arguments if parsed is None else parsed


def tool_arguments_object_for_replay(arguments: Any) -> dict[str, Any]:
    """Return object-shaped arguments for provider history replay only.

    Replay may repair malformed JSON to meet the provider protocol’s object
    requirement. Do not use it for
    newly generated tool calls that are about to execute.
    """
    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        return cast(dict[str, Any], arguments)
    if not isinstance(arguments, str):
        return {}

    stripped = arguments.strip()
    if not stripped:
        return {}

    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, RecursionError):
        try:
            import json_repair

            parsed = json_repair.loads(stripped)
        except (ValueError, RecursionError):
            return {}
    return cast(dict[str, Any], parsed) if isinstance(parsed, dict) else {}


def tool_arguments_json_for_replay(arguments: Any) -> str:
    """Return JSON object string arguments for provider history replay only."""
    return json.dumps(tool_arguments_object_for_replay(arguments), ensure_ascii=False)
