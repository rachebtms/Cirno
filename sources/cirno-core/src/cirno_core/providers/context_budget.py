"""Shared context admission and per-request output ceilings."""

from dataclasses import dataclass
from math import ceil

CONTEXT_SAFETY_BUFFER = 1024


@dataclass(frozen=True, slots=True)
class ContextBudget:
    window_tokens: int | None
    output_tokens: int
    reserve_percent: int = 5
    compact_percent: int = 100

    @property
    def reserve_tokens(self) -> int:
        if not self.window_tokens:
            return self.output_tokens
        return min(self.output_tokens, ceil(self.window_tokens * self.reserve_percent / 100))

    @property
    def input_limit(self) -> int:
        if not self.window_tokens:
            return 0
        return max(0, min(
            self.window_tokens - self.reserve_tokens - CONTEXT_SAFETY_BUFFER,
            self.window_tokens * self.compact_percent // 100,
        ))

    def output_limit(self, input_tokens: int) -> int:
        if not self.window_tokens:
            return self.output_tokens
        available = self.window_tokens - input_tokens - CONTEXT_SAFETY_BUFFER
        if available <= 0:
            raise ValueError(
                f"No output space remains in the context window: {input_tokens}/{self.window_tokens} input tokens"
            )
        return min(self.output_tokens, available)
