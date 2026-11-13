"""Tests for build_status_content cache hit rate display."""

from cirno_usage.types import LLMUsage
from cirno_core.utils.runtime_status import build_status_content


def test_status_shows_cache_hit_rate():
    content = build_status_content(
        version="0.1.0",
        model="glm-4-plus",
        start_time=1000000.0,
        last_usage=LLMUsage.reported(input_tokens=2000, output_tokens=300, cache_read_tokens=1200),
        context_window_tokens=128000,
        session_msg_count=10,
        context_tokens_estimate=5000,
    )
    assert "60% cached" in content
    assert "2000 in / 300 out" in content
    assert "Tasks: 0 active" in content


def test_status_no_cache_info():
    """Without a reported cache-read count, omit the cache percentage."""
    content = build_status_content(
        version="0.1.0",
        model="glm-4-plus",
        start_time=1000000.0,
        last_usage=LLMUsage.reported(input_tokens=2000, output_tokens=300),
        context_window_tokens=128000,
        session_msg_count=10,
        context_tokens_estimate=5000,
    )
    assert "cached" not in content.lower()
    assert "2000 in / 300 out" in content
    assert "Tasks: 0 active" in content


def test_status_zero_cache_read_tokens():
    """An explicit zero cache-read count should not show cache percentage."""
    content = build_status_content(
        version="0.1.0",
        model="glm-4-plus",
        start_time=1000000.0,
        last_usage=LLMUsage.reported(input_tokens=2000, output_tokens=300, cache_read_tokens=0),
        context_window_tokens=128000,
        session_msg_count=10,
        context_tokens_estimate=5000,
    )
    assert "cached" not in content.lower()


def test_status_100_percent_cached():
    content = build_status_content(
        version="0.1.0",
        model="glm-4-plus",
        start_time=1000000.0,
        last_usage=LLMUsage.reported(input_tokens=1000, output_tokens=100, cache_read_tokens=1000),
        context_window_tokens=128000,
        session_msg_count=5,
        context_tokens_estimate=3000,
    )
    assert "100% cached" in content


def test_status_context_pct_uses_budget_not_total():
    """Percentage should be calculated against input budget, not raw context window."""
    content = build_status_content(
        version="0.1.0",
        model="test",
        start_time=1000000.0,
        last_usage=LLMUsage.reported(input_tokens=2000, output_tokens=300),
        context_window_tokens=128000,
        session_msg_count=10,
        context_tokens_estimate=120000,
        max_completion_tokens=8192,
    )
    # The shared budget reserves 5%, rather than the entire configured output ceiling.
    assert "(99% of input budget)" in content


def test_status_context_pct_capped_at_999():
    """Extreme overflow should be capped at 999."""
    content = build_status_content(
        version="0.1.0",
        model="test",
        start_time=1000000.0,
        last_usage=LLMUsage.reported(input_tokens=2000, output_tokens=300),
        context_window_tokens=10000,
        session_msg_count=10,
        context_tokens_estimate=100000,
        max_completion_tokens=4096,
    )
    assert "(999% of input budget)" in content


def test_status_large_output_ceiling_does_not_consume_the_whole_context():
    from cirno_core.providers.context_budget import ContextBudget

    for reserve, compact in [(5, 100), (10, 80)]:
        budget = ContextBudget(512_000, 500_000, reserve, compact)
        content = build_status_content(
            version="test", model="test", start_time=0, last_usage=None,
            context_window_tokens=512_000, session_msg_count=10,
            context_tokens_estimate=256_000, max_completion_tokens=500_000,
            output_reserve_percent=reserve, active_compact_percent=compact,
        )
        assert f"({int(256_000 / budget.input_limit * 100)}% of input budget)" in content
