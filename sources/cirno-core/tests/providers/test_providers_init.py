"""Tests for lazy provider exports from cirno.providers."""

from __future__ import annotations

import importlib
import sys


def test_importing_providers_package_is_lazy(monkeypatch) -> None:
    original_package = sys.modules["cirno.providers"]
    monkeypatch.delitem(sys.modules, "cirno.providers", raising=False)
    monkeypatch.delitem(sys.modules, "cirno.providers.anthropic_provider", raising=False)
    monkeypatch.delitem(sys.modules, "cirno.providers.openai_compat_provider", raising=False)
    monkeypatch.delitem(sys.modules, "cirno.providers.openai_codex_provider", raising=False)
    monkeypatch.delitem(sys.modules, "cirno.providers.xai_oauth", raising=False)
    monkeypatch.delitem(sys.modules, "cirno.providers.xai_grok_provider", raising=False)
    monkeypatch.delitem(sys.modules, "cirno.providers.github_copilot_provider", raising=False)
    monkeypatch.delitem(sys.modules, "cirno.providers.azure_openai_provider", raising=False)
    monkeypatch.delitem(sys.modules, "cirno.providers.bedrock_provider", raising=False)

    try:
        providers = importlib.import_module("cirno.providers")

        assert "cirno.providers.anthropic_provider" not in sys.modules
        assert "cirno.providers.openai_compat_provider" not in sys.modules
        assert "cirno.providers.openai_codex_provider" not in sys.modules
        assert "cirno.providers.xai_oauth" not in sys.modules
        assert "cirno.providers.xai_grok_provider" not in sys.modules
        assert "cirno.providers.github_copilot_provider" not in sys.modules
        assert "cirno.providers.azure_openai_provider" not in sys.modules
        assert "cirno.providers.bedrock_provider" not in sys.modules
        assert providers.__all__ == [
            "LLMProvider",
            "LLMResponse",
            "LLMUsage",
            "AnthropicProvider",
            "OpenAICompatProvider",
            "OpenAICodexProvider",
            "XAIGrokProvider",
            "GitHubCopilotProvider",
            "AzureOpenAIProvider",
            "BedrockProvider",
        ]
    finally:
        # Importing a replacement subpackage also replaces cirno.providers on the
        # parent package. Restore both views so this isolation test cannot pollute
        # later tests that resolve a module through a dotted monkeypatch target.
        monkeypatch.undo()
        setattr(sys.modules["cirno"], "providers", original_package)


def test_explicit_provider_import_still_works(monkeypatch) -> None:
    original_package = sys.modules["cirno.providers"]
    monkeypatch.delitem(sys.modules, "cirno.providers", raising=False)
    monkeypatch.delitem(sys.modules, "cirno.providers.anthropic_provider", raising=False)

    try:
        namespace: dict[str, object] = {}
        exec("from cirno.providers import AnthropicProvider", namespace)

        assert namespace["AnthropicProvider"].__name__ == "AnthropicProvider"
        assert "cirno.providers.anthropic_provider" in sys.modules
    finally:
        monkeypatch.undo()
        setattr(sys.modules["cirno"], "providers", original_package)
