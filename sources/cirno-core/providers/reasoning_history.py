"""Model-owned replay policy for plaintext reasoning; native signatures stay intact."""
from __future__ import annotations

from copy import deepcopy


def history_policy(provider, *, tools=None, for_count=False):
    policy = getattr(provider, "reasoning_history", "auto")
    spec = getattr(provider, "_spec", None)
    if tools and spec is not None and spec.name == "deepseek" and policy == "omit":
        raise ValueError("DeepSeek tool requests require reasoning history. Select Automatic or Preserve.")
    if for_count and spec is not None and spec.name == "deepseek" and not tools:
        return "omit"
    if policy not in {"auto", "preserve", "omit"}:
        policy = "auto"
    if policy != "auto":
        return policy
    if spec is not None and (spec.strip_history_reasoning_content is True):
        return "omit"
    return "preserve"


def prepare_reasoning_history(provider, messages, *, tools=None, for_count=False):
    """Change a request copy only, never the saved transcript or signed blocks."""
    if history_policy(provider, tools=tools, for_count=for_count) != "omit":
        return messages
    result = deepcopy(messages)
    for message in result:
        message.pop("reasoning_content", None)
    return result


def requires_tool_reasoning_history(provider):
    from cirno_core.providers.fallback_provider import FallbackProvider

    if isinstance(provider, FallbackProvider):
        return requires_tool_reasoning_history(provider._primary)
    spec = getattr(provider, "_spec", None)
    return spec is not None and spec.name == "deepseek"
