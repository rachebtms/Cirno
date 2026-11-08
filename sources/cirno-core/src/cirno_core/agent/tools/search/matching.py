"""Regex matching that observes the same deadline as filesystem traversal."""

import time

import regex
from cirno_core.agent.tools.search.budget import SearchBudget, SearchBudgetExceededError


class SearchPattern:
    def __init__(
        self,
        pattern: str,
        budget: SearchBudget,
        *,
        fixed_strings: bool,
        case_insensitive: bool,
    ) -> None:
        self._budget = budget
        flags = regex.VERSION0 | (regex.IGNORECASE if case_insensitive else 0)
        try:
            self._pattern = regex.compile(
                regex.escape(pattern) if fixed_strings else pattern, flags
            )
        except regex.error as error:
            raise ValueError(f"invalid regex pattern: {error}") from error

    def search(self, text: str) -> regex.Match[str] | None:
        self._budget.checkpoint()
        remaining = self._budget.deadline - time.monotonic()
        if remaining <= 0:
            raise SearchBudgetExceededError("time")
        try:
            return self._pattern.search(text, timeout=remaining, concurrent=True)
        except TimeoutError as error:
            raise SearchBudgetExceededError("time") from error
