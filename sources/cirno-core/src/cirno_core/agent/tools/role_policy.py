"""Per-run role admission shared by native and nested PTC tool execution."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

from cirno_core.agent.tools.naming import implementation_name
from cirno_core.session.roles import ConversationRole

# Coordination remains available after direct work exhausts its budget. The
# schema stays unchanged: only execution admission changes, preserving caching.
_COORDINATION = frozenset({
    "message", "ask_user", "cancel_ask", "create_session", "set_session_title",
    "search_sessions", "read_session", "send_session_message", "report_work",
    "control_session", "control_goal", "project", "create_goal", "get_goal", "update_goal",
})


def is_coordination_tool(name: str) -> bool:
    return implementation_name(name) in _COORDINATION


class RoleToolPolicy:
    def __init__(self, role: ConversationRole):
        self.role = role
        self.calls = 0
        self.seconds = 0.0
        self._active = 0
        self._started = 0.0

    def remaining(self, name: str) -> float | None:
        """Reject unavailable work before approval without charging approval time."""
        name = implementation_name(name)
        if not self.role.allows_tool(name):
            raise ValueError(f"Tool {name} is unavailable to the {self.role.name} role")
        limits = self.role.direct_execution
        if limits is None or is_coordination_tool(name):
            return None
        current = time.monotonic()
        occupied = current - self._started if self._active else 0
        remaining = limits.max_seconds - self.seconds - occupied
        if self.calls >= limits.max_calls or remaining <= 0:
            raise ValueError(
                "Router direct-execution budget exhausted. Stop ordinary tool work and create "
                "a Worker with conversations__create. Pass the original request, completed "
                "results and unresolved work; do not repeat completed effects. "
                "User replies and coordination tools remain available."
            )
        return remaining

    @staticmethod
    @asynccontextmanager
    async def _deadline(seconds: float):
        deadline = asyncio.timeout(seconds)
        try:
            async with deadline:
                yield
        except TimeoutError as exc:
            if not deadline.expired():
                raise
            raise TimeoutError(
                "Router direct work exceeded its small-task time budget. Delegate unfinished "
                "work to a Worker. The interrupted operation may have completed effects; "
                "inspect its state before retrying."
            ) from exc

    @asynccontextmanager
    async def admit(self, name: str):
        name = implementation_name(name)
        remaining = self.remaining(name)
        if remaining is None:
            yield
            return
        # Charge a PTC program's wall time once, together with any nested work.
        # Its nested operations own the call count; the wrapper is not a second
        # ordinary call. Direct coordination stays available after exhaustion.
        if name != "run_code":
            self.calls += 1
        if not self._active:
            self._started = time.monotonic()
        self._active += 1
        try:
            async with self._deadline(remaining):
                yield
        finally:
            self._active -= 1
            if not self._active:
                self.seconds += time.monotonic() - self._started
