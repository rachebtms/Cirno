"""Public tool contracts and discovery interfaces."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cirno.agent.tools.base import Schema, Tool, ToolResult, tool_parameters
    from cirno.agent.tools.context import ToolContext
    from cirno.agent.tools.loader import ToolLoader
    from cirno.agent.tools.registry import ToolRegistry
    from cirno.agent.tools.schema import (
        ArraySchema,
        BooleanSchema,
        IntegerSchema,
        NumberSchema,
        ObjectSchema,
        StringSchema,
        tool_parameters_schema,
    )


_EXPORTS = {
    "Schema": "cirno.agent.tools.base",
    "ArraySchema": "cirno.agent.tools.schema",
    "BooleanSchema": "cirno.agent.tools.schema",
    "IntegerSchema": "cirno.agent.tools.schema",
    "NumberSchema": "cirno.agent.tools.schema",
    "ObjectSchema": "cirno.agent.tools.schema",
    "StringSchema": "cirno.agent.tools.schema",
    "Tool": "cirno.agent.tools.base",
    "ToolContext": "cirno.agent.tools.context",
    "ToolLoader": "cirno.agent.tools.loader",
    "ToolResult": "cirno.agent.tools.base",
    "ToolRegistry": "cirno.agent.tools.registry",
    "tool_parameters": "cirno.agent.tools.base",
    "tool_parameters_schema": "cirno.agent.tools.schema",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))


__all__ = [
    "Schema",
    "ArraySchema",
    "BooleanSchema",
    "IntegerSchema",
    "NumberSchema",
    "ObjectSchema",
    "StringSchema",
    "Tool",
    "ToolContext",
    "ToolLoader",
    "ToolResult",
    "ToolRegistry",
    "tool_parameters",
    "tool_parameters_schema",
]
