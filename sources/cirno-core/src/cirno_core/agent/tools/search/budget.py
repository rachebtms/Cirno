"""Cooperative cancellation and limits for filesystem search workers."""

import threading
import time
from dataclasses import dataclass


class SearchCancelledError(Exception):
    """Stop a worker scan after its owning async task was cancelled."""


class SearchBudgetExceededError(Exception):
    """Stop an unbounded filesystem scan at its configured budget."""


@dataclass(slots=True)
class SearchBudget:
    cancelled: threading.Event
    deadline: float
    max_paths: int
    scanned_paths: int = 0

    def checkpoint(self) -> None:
        if self.cancelled.is_set():
            raise SearchCancelledError
        if time.monotonic() >= self.deadline:
            raise SearchBudgetExceededError("time")

    def visit_path(self) -> None:
        self.checkpoint()
        self.scanned_paths += 1
        if self.scanned_paths > self.max_paths:
            raise SearchBudgetExceededError("paths")
