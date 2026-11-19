"""Keep credential values out of tool activity, checkpoints and request logs."""

from __future__ import annotations

import json


def tool_arguments(name: str, arguments):
    if name == "credential" or name.replace("__", ".").startswith("credentials."):
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except (json.JSONDecodeError, RecursionError):
                return {"invalid_arguments": "[credential arguments omitted]"}
        if isinstance(arguments, dict):
            return {
                key: "[encrypted credential]" if key in {"value", "username", "ssh"} else value
                for key, value in arguments.items()
            }
        return {"invalid_arguments": "[credential arguments omitted]"}
    return arguments


CREDENTIAL_RESULT_HIDDEN = "[Credential read result hidden; read the saved credential again when needed.]"


def is_sensitive_result(name: str, result, arguments=None) -> bool:
    """Identify the explicit secret-return channel, without guessing secret patterns."""
    if getattr(result, "sensitive", False):
        return True
    if getattr(result, "is_error", False):
        return False
    if name.replace("__", ".") == "credentials.read":
        return True
    if name != "credential":
        return False
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except (ValueError, TypeError):
            return False
    return isinstance(arguments, dict) and arguments.get("action") == "read"


def tool_result(name: str, result, arguments=None):
    """Hide a secret for storage/display; callers keep the live result separately."""
    return CREDENTIAL_RESULT_HIDDEN if is_sensitive_result(name, result, arguments) else result


def _durable_arguments(name, arguments):
    safe = tool_arguments(name, arguments)
    if isinstance(arguments, str) and safe is not arguments:
        try:
            if json.loads(arguments) == safe:
                return arguments  # Preserve exact non-sensitive prefix bytes.
        except (ValueError, RecursionError):
            pass
        safe = json.dumps(safe, ensure_ascii=False)
    return safe


def tool_history(messages: list[dict]) -> list[dict]:
    """Copy sensitive results in Chat/Responses history; preserve every call ID and order."""
    calls = {}
    for message in messages:
        if not isinstance(message, dict):
            continue  # Preserve opaque, provider-owned items unchanged.
        if message.get("type") == "function_call":
            calls[message.get("call_id")] = (message.get("name", ""), message.get("arguments"))
        for call in message.get("tool_calls") or []:
            if isinstance(call, dict) and isinstance(function := call.get("function"), dict):
                calls[call.get("id")] = (function.get("name", ""), function.get("arguments"))
    updated = messages
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        replacement = message
        if message.get("type") == "function_call":
            arguments = message.get("arguments")
            safe = _durable_arguments(message.get("name", ""), arguments)
            if safe != arguments:
                replacement = {**message, "arguments": safe}
        if message.get("role") == "assistant" and message.get("tool_calls"):
            safe_calls = []
            for call in message["tool_calls"]:
                function = call.get("function") if isinstance(call, dict) else None
                if isinstance(function, dict):
                    arguments = function.get("arguments")
                    safe = _durable_arguments(function.get("name", ""), arguments)
                    if safe != arguments:
                        call = {**call, "function": {**function, "arguments": safe}}
                safe_calls.append(call)
            if safe_calls != message["tool_calls"]:
                replacement = {**message, "tool_calls": safe_calls}
        if replacement is not message:
            if updated is messages:
                updated = list(messages)
            updated[index] = replacement
        if message.get("role") == "tool":
            name, arguments = calls.get(message.get("tool_call_id"), (message.get("name", ""), None))
            name = message.get("name") or name
            key = "content"
        elif message.get("type") == "function_call_output":
            name, arguments = calls.get(message.get("call_id"), ("", None))
            key = "output"
        else:
            continue
        value = tool_result(name, message.get(key), arguments)
        if value != message.get(key):
            if updated is messages:
                updated = list(messages)
            updated[index] = {**message, key: value}
    return updated
