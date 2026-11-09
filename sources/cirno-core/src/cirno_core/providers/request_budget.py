"""Apply the context ceiling to each physical call, including fallback models."""

from typing import TYPE_CHECKING, Any

from cirno_core.providers.context_budget import ContextBudget
from cirno_core.providers.contracts import ProviderCallContext
from cirno_core.utils.token_estimation import estimate_prompt_tokens_chain

if TYPE_CHECKING:
    from cirno_core.providers.base import LLMProvider


def bound_request_output(provider: "LLMProvider", kwargs: dict[str, Any]) -> dict[str, Any]:
    context = kwargs.get("provider_context")
    if not isinstance(context, ProviderCallContext) or not context.context_window_tokens:
        return kwargs
    # This adapter must first compact its opaque state; its pre-request budget owns admission.
    if context.compaction_input_budget is not None:
        return kwargs
    tokens = context.input_tokens
    if tokens is None:
        tokens, _ = estimate_prompt_tokens_chain(
            provider, kwargs.get("model"), kwargs["messages"], kwargs.get("tools"),
        )
    max_output = kwargs["max_tokens"] if "max_tokens" in kwargs else provider.generation.max_tokens
    budget = ContextBudget(context.context_window_tokens, max_output)
    return {**kwargs, "max_tokens": budget.output_limit(tokens)}
