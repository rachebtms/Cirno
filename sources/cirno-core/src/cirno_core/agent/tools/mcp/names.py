"""MCP names."""

from __future__ import annotations

import hashlib
import re

_SANITIZE_RE = re.compile(r"_+")


_MAX_TOOL_NAME_LENGTH = 64


_HASH_LENGTH = 8


def _sanitize_name(name: str) -> str:
    """Sanitize an MCP-derived name for model API compatibility."""
    return _SANITIZE_RE.sub("_", re.sub(r"[^a-zA-Z0-9_-]", "_", name))


def _limit_tool_name(name: str, max_length: int = _MAX_TOOL_NAME_LENGTH) -> str:
    """Limit a tool name while keeping short names unchanged."""
    if len(name) <= max_length:
        return name

    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:_HASH_LENGTH]
    prefix_length = max_length - _HASH_LENGTH - 1
    return f"{name[:prefix_length]}_{digest}"


def _sanitize_mcp_tool_name(name: str) -> str:
    """Keep distinct upstream names distinct after provider wire normalization."""
    sanitized = _sanitize_name(name)
    if sanitized != name:
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:_HASH_LENGTH]
        sanitized = f"{sanitized}_{digest}"
    return _limit_tool_name(sanitized)


def _tool_prefix(server_name: str) -> str:
    return _sanitize_name(f"mcp_{server_name}_")
