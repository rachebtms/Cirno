"""Malformed accounting cannot discard an otherwise valid provider answer."""

import pytest
from cirno_core.providers.chat_completions.complete import parse_response
from cirno_core.providers.chat_completions.streaming import ChatStreamAccumulator
from cirno_core.providers.chat_completions.usage import extract_usage


@pytest.mark.parametrize("transport", ["complete", "stream"])
@pytest.mark.parametrize("field,value", [("prompt_tokens", -1), ("completion_tokens", "bad"),
                                         ("prompt_tokens", float("inf")), ("completion_tokens", True)])
def test_invalid_primary_usage_keeps_the_response_content(transport, field, value):
    wire = {"usage": {"prompt_tokens": 100, "completion_tokens": 5, field: value},
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"content": "Fixture"}, "delta": {"content": "Fixture"}}]}
    if transport == "complete":
        response = parse_response(wire)
    else:
        stream = ChatStreamAccumulator()
        assert stream.consume(wire).content == "Fixture"
        response = stream.response()
    assert response.content == "Fixture" and response.finish_reason == "stop"
    assert response.usage is None


@pytest.mark.parametrize("cached", [-3, float("inf"), 120])
def test_invalid_optional_cache_metric_keeps_valid_reported_token_counts(cached):
    usage = extract_usage({"usage": {"prompt_tokens": 100, "completion_tokens": 5,
                                      "prompt_tokens_details": {"cached_tokens": cached}}})
    assert usage is not None and usage.input_tokens == 100 and usage.output_tokens == 5
    assert usage.total_tokens == 105 and usage.cache_read_tokens is None


def test_inconsistent_cache_partition_is_unknown_without_losing_reported_counts():
    usage = extract_usage({"usage": {"prompt_tokens": 100, "completion_tokens": 5,
                                      "prompt_tokens_details": {"cached_tokens": 60, "cache_write_tokens": 60}}})
    assert usage is not None and usage.total_tokens == 105
    assert usage.cache_read_tokens is None and usage.cache_write_tokens is None


def test_invalid_total_does_not_turn_an_explicit_zero_cache_into_a_miss():
    usage = extract_usage({"usage": {"prompt_tokens": 100, "completion_tokens": 5,
                                      "total_tokens": float("inf"), "prompt_tokens_details": {"cached_tokens": 0}}})
    assert usage is not None and usage.total_tokens == 105 and usage.cache_read_tokens == 0
