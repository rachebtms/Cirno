"""Compact same-turn nudges without changing accepted Goal/history messages."""

from cirno_core.session.goal_state import goal_state_raw, goal_state_runtime_lines, parse_goal_state


class GoalContinuation:
    def __init__(self):
        self._last = None

    def message(self, metadata):
        lines = goal_state_runtime_lines(metadata)
        if not lines:
            self._last = None
            return None
        goal = parse_goal_state(goal_state_raw(metadata)) or {}
        snapshot = (goal.get("goal_id"), tuple(lines))
        if snapshot == self._last:
            return (
                "Continue the unchanged active Goal already in context. Use tools for remaining work; "
                "do not repeat completed actions. Update the Goal if complete or waiting."
            )
        self._last = snapshot
        return (
            "You have an active sustained goal:\n\n" + "\n".join(lines)
            + "\n\nPlease continue working toward the objective using your tools, "
            "or call goals__update with action='complete' if the work is truly finished."
        )
