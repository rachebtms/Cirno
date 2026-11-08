"""Human-readable runtime status summaries."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cirno_usage.types import LLMUsage


def build_status_content(
    *,
    version: str,
    model: str,
    start_time: float,
    last_usage: LLMUsage | None,
    context_window_tokens: int,
    session_msg_count: int,
    context_tokens_estimate: int,
    search_usage_text: str | None = None,
    active_task_count: int = 0,
    max_completion_tokens: int = 8192,
) -> str:
    """Build a human-readable runtime status snapshot.

    Args:
        search_usage_text: Optional pre-formatted web search usage string
                           (produced by SearchUsageInfo.format()). When provided
                           it is appended as an extra section.
    """
    uptime_s = int(time.time() - start_time)
    uptime = (
        f"{uptime_s // 3600}h {(uptime_s % 3600) // 60}m"
        if uptime_s >= 3600
        else f"{uptime_s // 60}m {uptime_s % 60}s"
    )
    last_in = last_usage.input_tokens if last_usage else 0
    last_out = last_usage.output_tokens if last_usage else 0
    cached = last_usage.cache_read_tokens if last_usage else None
    ctx_total = max(context_window_tokens, 0)
    # Budget mirrors Consolidator formula: ctx_window - max_completion - _SAFETY_BUFFER
    ctx_budget = max(ctx_total - int(max_completion_tokens) - 1024, 1)
    ctx_pct = min(int((context_tokens_estimate / ctx_budget) * 100), 999) if ctx_budget > 0 else 0
    ctx_used_str = (
        f"{context_tokens_estimate // 1000}k"
        if context_tokens_estimate >= 1000
        else str(context_tokens_estimate)
    )
    ctx_total_str = f"{ctx_total // 1000}k" if ctx_total > 0 else "n/a"
    token_line = f"\U0001f4ca Tokens: {last_in} in / {last_out} out"
    if cached and last_in:
        token_line += f" ({cached * 100 // last_in}% cached)"
    lines = [
        f"❄️ Cirno v{version}",
        f"\U0001f9e0 Model: {model}",
        token_line,
        f"\U0001f4da Context: {ctx_used_str}/{ctx_total_str} ({ctx_pct}% of input budget)",
        f"\U0001f4ac Session: {session_msg_count} messages",
        f"\u23f1 Uptime: {uptime}",
        f"\u26a1 Tasks: {active_task_count} active",
    ]
    if search_usage_text:
        lines.append(search_usage_text)
    return "\n".join(lines)
