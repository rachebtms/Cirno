"""HTTP header identity shared by MCP settings and connection setup."""

from collections.abc import Mapping


def merge_mcp_headers(*sources: Mapping[str, str] | None) -> dict[str, str]:
    """Replace equivalent names with the last value, retaining its spelling."""
    merged: dict[str, tuple[str, str]] = {}
    for source in sources:
        for name, value in (source or {}).items():
            merged[name.lower()] = (name, value)
    return dict(merged.values())
