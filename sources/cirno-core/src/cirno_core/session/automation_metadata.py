"""Saved automation addresses are independent of the turn that created them."""

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from cirno_core.bus.delivery import DELIVERY_RUN_META
from cirno_core.runtime.context import RUNTIME_CONTEXT_INPUT_META, WEBUI_QUOTE_METADATA
from cirno_core.security.workspace_access import WORKSPACE_SCOPE_METADATA_KEY
from cirno_core.session.display_history import HISTORY_GENERATION_METADATA_KEY
from cirno_core.session.recovery.contracts import (
    PENDING_FOLLOWUP_ID_KEY,
    RECOVERY_INBOUND_METADATA_KEY,
    REQUEST_ORIGIN_METADATA_KEY,
)
from cirno_core.session.session_messages import SESSION_MESSAGE_METADATA_KEY
from cirno_core.session.transport_metadata import WEBSOCKET_TURN_OWNER_METADATA_KEY, WEBUI_TURN_METADATA_KEY
from cirno_core.session.turn_continuation import (
    INTERNAL_CONTINUATION_KIND_META,
    INTERNAL_CONTINUATION_META,
    INTERNAL_CONTINUATION_RUN_STARTED_AT_META,
    SKIP_USER_PERSIST_META,
)

_CREATING_TURN_FIELDS = frozenset({
    HISTORY_GENERATION_METADATA_KEY, WEBUI_TURN_METADATA_KEY, WEBSOCKET_TURN_OWNER_METADATA_KEY,
    DELIVERY_RUN_META,
    WORKSPACE_SCOPE_METADATA_KEY,
    RUNTIME_CONTEXT_INPUT_META, WEBUI_QUOTE_METADATA, REQUEST_ORIGIN_METADATA_KEY,
    RECOVERY_INBOUND_METADATA_KEY, PENDING_FOLLOWUP_ID_KEY,
    SESSION_MESSAGE_METADATA_KEY, "_work_report", "_hidden_history",
    INTERNAL_CONTINUATION_META, INTERNAL_CONTINUATION_KIND_META,
    INTERNAL_CONTINUATION_RUN_STARTED_AT_META, SKIP_USER_PERSIST_META,
    "goal_requested", "goal_started_at", "original_command", "original_content",
    "_goal_id", "_approval_decision", "_supervisor_control", "_heartbeat",
})


def automation_origin_metadata(source: Mapping[str, Any] | None) -> dict[str, Any]:
    """Retain channel routing without old execution authority or access policy.

    Apply both when saving new automations and when dispatching legacy payloads.
    Coordination envelopes and report markers belong to the creating input,
    not to later invocations; keeping them would reuse its durable receipt.
    The normal admission path binds each invocation to its current destination
    and resolves its current conversation workspace/access settings.
    """
    return deepcopy({key: value for key, value in (source or {}).items() if key not in _CREATING_TURN_FIELDS})
