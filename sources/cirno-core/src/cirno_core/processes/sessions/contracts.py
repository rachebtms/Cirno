"""Execution-session budgets, observations and process status."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DEFAULT_YIELD_MS = 1000
MAX_YIELD_MS = 30_000
DEFAULT_WAIT_FOR_MS = 10_000
DEFAULT_UNTIL_EXIT_MS = 600_000
MAX_WAIT_FOR_MS = 600_000
DEFAULT_MAX_OUTPUT_CHARS = 10_000
MAX_OUTPUT_CHARS = 50_000


FinishReason = Literal[
    "exit",
    "max_runtime",
    "idle_timeout",
    "cancelled",
    "owner_closed",
    "shutdown",
    "execution_error",
]


@dataclass(slots=True)
class SessionPoll:
    output: str
    done: bool
    exit_code: int | None
    elapsed_s: float = 0.0
    finish_reason: FinishReason | None = None
    stopping: bool = False
    output_idle_s: float = 0.0
    idle_timeout: int = 0
    remaining_s: float | None = None
    stdin_closed: bool = False
    truncated_chars: int = 0
    output_incomplete: bool = False
    execution_error: str | None = None

    @property
    def failed(self) -> bool:
        return self.timed_out or self.finish_reason == "execution_error"

    @property
    def timed_out(self) -> bool:
        return self.finish_reason in ("max_runtime", "idle_timeout")

    @property
    def terminated(self) -> bool:
        return self.finish_reason in ("cancelled", "owner_closed", "shutdown")


@dataclass(slots=True)
class ExecSessionInfo:
    session_id: str
    command: str
    cwd: str
    elapsed_s: float
    idle_s: float
    remaining_s: float | None
    returncode: int | None
    owner_session_key: str | None = None
    idle_timeout: int = 0
    stopping: bool = False
    finish_reason: FinishReason | None = None
    cleanup_error: str | None = None
