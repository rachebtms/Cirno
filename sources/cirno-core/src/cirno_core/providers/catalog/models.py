"""Model families shared by metadata and request policies."""

KIMI_K3_MODELS: frozenset[str] = frozenset(
    {
        "kimi-k3",
        "kimi-k3.1-pro",
        "kimi-k3.1-pro-highspeed",
    }
)


_DEEPSEEK_REASONING_EFFORTS = ("none", "low", "high", "max")
