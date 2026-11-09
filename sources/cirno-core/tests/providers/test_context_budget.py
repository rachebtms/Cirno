"""Large output ceilings must not consume the conversation's entire input window."""
import pytest

from cirno_core.providers.context_budget import ContextBudget
from cirno_core.providers.contracts import ProviderCallContext
from cirno_core.providers.request_budget import bound_request_output


@pytest.mark.parametrize("output", [256_000, 512_000])
def test_large_output_ceiling_keeps_95_percent_of_window_usable(output):
    budget = ContextBudget(512_000, output)
    assert budget.input_limit == 485_376
    assert budget.output_limit(300_000) == 210_976
    assert budget.output_limit(100_000) == min(output, 410_976)
    assert ContextBudget(512_000, output, compact_percent=80).input_limit == 409_600


def test_physical_call_does_not_mutate_configuration_and_recalculates_each_request():
    from types import SimpleNamespace
    from cirno_core.providers.generation import GenerationSettings
    provider = SimpleNamespace(generation=GenerationSettings(max_tokens=512_000))
    context = ProviderCallContext(context_window_tokens=512_000, input_tokens=300_000)
    kwargs = {"messages": [], "max_tokens": 512_000, "provider_context": context}
    assert bound_request_output(provider, kwargs)["max_tokens"] == 210_976
    assert kwargs["max_tokens"] == 512_000
    kwargs["provider_context"] = ProviderCallContext(context_window_tokens=512_000, input_tokens=100_000)
    assert bound_request_output(provider, kwargs)["max_tokens"] == 410_976


def test_exhausted_window_is_explicit_not_a_zero_token_request():
    with pytest.raises(ValueError, match="No output space remains"):
        ContextBudget(512_000, 512_000).output_limit(511_000)
