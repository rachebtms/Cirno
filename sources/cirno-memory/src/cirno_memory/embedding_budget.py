"""One wall-clock inference budget shared by all batches of a search."""
from __future__ import annotations

import time


class EmbeddingBudget:
    def __init__(self, seconds: float):
        self.seconds = seconds
        self.deadline = time.monotonic() + seconds

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Embedding search exceeded its {self.seconds:g} second time budget; using BM25")
        return remaining
