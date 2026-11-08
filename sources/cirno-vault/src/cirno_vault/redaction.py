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
