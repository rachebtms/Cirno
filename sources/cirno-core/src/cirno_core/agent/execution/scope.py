"""Detach workspace metadata before background prompt preparation."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from cirno_core.security.workspace_access import (
    WORKSPACE_SCOPE_METADATA_KEY,
)


def _prompt_scope_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Detach only the metadata consumed by workspace scope resolution."""
    key = WORKSPACE_SCOPE_METADATA_KEY
    return {key: deepcopy(metadata[key])} if key in metadata else {}
