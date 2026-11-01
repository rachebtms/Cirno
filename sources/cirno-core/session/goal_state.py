"""Session metadata helpers for explicit sustained goals.

Tools set ``metadata[GOAL_STATE_KEY]``. Callers use
``goal_state_runtime_lines`` and ``goal_state_ws_blob`` without
importing tool implementations.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, cast

GOAL_STATE_KEY = "goal_state"
GOAL_COMMAND = "/goal"
MAX_GOAL_OBJECTIVE_CHARS = 4000
_MAX_OBJECTIVE_WS = 600


def _session_goal_raw(metadata: Mapping[str, Any] | None) -> Any:
    if not metadata:
        return None
    return metadata.get(GOAL_STATE_KEY)


def goal_state_raw(metadata: Mapping[str, Any] | None) -> Any:
    """Return the session goal blob under :data:`GOAL_STATE_KEY`."""
    return _session_goal_raw(metadata)


def sustained_goal_active(metadata: Mapping[str, Any] | None) -> bool:
    """True when this session has an active sustained objective."""
    goal = parse_goal_state(goal_state_raw(metadata))
    return isinstance(goal, dict) and goal.get("status") == "active"


def explicit_goal_requested(message_metadata: Mapping[str, Any] | None) -> bool:
    """True when this turn was explicitly started by the ``/goal`` command."""
    if not message_metadata:
        return False
    if message_metadata.get("goal_requested") is True:
        return True
    return str(message_metadata.get("original_command") or "").strip() == GOAL_COMMAND


def sustained_goal_turn(
    metadata: Mapping[str, Any] | None,
    *,
    message_metadata: Mapping[str, Any] | None = None,
) -> bool:
    """True when this turn should use sustained-goal runtime limits."""
    return sustained_goal_active(metadata) or explicit_goal_requested(message_metadata)


def parse_goal_state(blob: Any) -> dict[str, Any] | None:
    if blob is None:
        return None
    if isinstance(blob, dict):
        return cast(dict[str, Any], blob)
    if isinstance(blob, str):
        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError:
            return None
        return cast(dict[str, Any], parsed) if isinstance(parsed, dict) else None
    return None


def goal_state_runtime_lines(metadata: Mapping[str, Any] | None) -> list[str]:
    """Lines appended inside the Runtime Context block when a goal is active."""
    if not metadata:
        return []
    goal = parse_goal_state(_session_goal_raw(metadata))
    if not isinstance(goal, dict) or goal.get("status") != "active":
        return []
    objective = str(goal.get("objective") or "").strip()
    if not objective:
        return ["Goal: active (no objective text stored)."]
    if len(objective) > MAX_GOAL_OBJECTIVE_CHARS:
        objective = objective[:MAX_GOAL_OBJECTIVE_CHARS].rstrip() + "\n… (truncated)"
    out = ["Goal (active):", objective]
    hint = str(goal.get("ui_summary") or "").strip()
    if hint:
        out.append(f"Summary: {hint}")
    out.append("Only call update_goal(action=complete) after the objective is achieved. A normal reply does not finish the Goal. Use wait with wake_after_seconds when no work is currently actionable.")
    if goal.get("recap"):
        out.append("Saved progress: " + str(goal["recap"]))
    return out


def goal_state_ws_blob(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """JSON-safe snapshot for WebSocket ``goal_state`` events (one chat_id per frame)."""
    goal = parse_goal_state(_session_goal_raw(metadata)) if metadata else None
    if isinstance(goal, dict) and goal.get("status") in {"active", "blocked", "paused", "waiting", "stopped"}:
        status = str(goal.get("status"))
        objective = str(goal.get("objective") or "").strip()
        if len(objective) > _MAX_OBJECTIVE_WS:
            objective = objective[:_MAX_OBJECTIVE_WS].rstrip() + "…"
        summary = str(goal.get("ui_summary") or "").strip()[:120]
        blob: dict[str, Any] = {"active": status == "active", "status": status}
        blob.update({key: goal[key] for key in ("goal_id", "continuation_limit", "wake_at") if key in goal})
        blob["continuation_rounds"] = (metadata or {}).get("_sustained_goal_continuation_rounds", 0)
        if summary:
            blob["ui_summary"] = summary
        if objective:
            blob["objective"] = objective
        recap = str(goal.get("recap") or "").strip()[:240]
        if recap:
            blob["recap"] = recap
        return blob
    return {"active": False}
