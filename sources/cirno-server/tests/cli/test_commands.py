import asyncio
import signal
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cirno_core.config.schema import Config
from cirno_core.cron.webui_metadata import cron_proactive_delivery_metadata
from cirno_core.memory.dream_run import commit_dream_changes
from cirno_core.memory.store import MemoryStore
from cirno_core.providers.factory import make_provider, provider_signature
from cirno_core.providers.openai_codex_provider import _strip_model_prefix
from cirno_core.providers.registry import find_by_name
from cirno_core.session.transport_metadata import (
    WEBUI_MESSAGE_SOURCE_METADATA_KEY,
    WEBUI_TURN_METADATA_KEY,
)
from cirno_server.cli import webui_support as cli_webui_support
from cirno_server.lifecycle import shutdown as server_shutdown


def test_proactive_websocket_delivery_gets_fresh_turn_id() -> None:
    metadata = {
        "webui": True,
        WEBUI_TURN_METADATA_KEY: "turn-that-created-the-reminder",
        "workspace_scope": {"mode": "default"},
    }

    out = cron_proactive_delivery_metadata(
        "websocket",
        metadata,
        turn_seed="cron:drink-water",
        source_label="drink water",
    )

    assert out["webui"] is True
    assert out["workspace_scope"] == {"mode": "default"}
    assert out[WEBUI_TURN_METADATA_KEY].startswith("cron:drink-water:")
    assert out[WEBUI_TURN_METADATA_KEY] != metadata[WEBUI_TURN_METADATA_KEY]
    assert out[WEBUI_MESSAGE_SOURCE_METADATA_KEY] == {"kind": "cron", "label": "drink water"}


def test_gateway_signal_handler_first_signal_stops_and_second_forces() -> None:
    class _FakeLoop:
        def __init__(self) -> None:
            self.handlers: dict[int, tuple[object, tuple[object, ...]]] = {}
            self.removed: list[int] = []

        def add_signal_handler(self, signum, callback, *args) -> None:
            self.handlers[int(signum)] = (callback, args)

        def remove_signal_handler(self, signum) -> bool:
            self.removed.append(int(signum))
            self.handlers.pop(int(signum), None)
            return True

    async def _run() -> None:
        loop = _FakeLoop()
        shutdown_event = asyncio.Event()
        never = asyncio.Event()
        task = asyncio.create_task(never.wait())
        output: list[str] = []

        tasks: list[asyncio.Task[object]] = []
        restore = server_shutdown.install_shutdown_handlers(
            loop, shutdown_event, tasks, output.append,
        )
        tasks.append(task)
        try:
            callback, args = loop.handlers[int(signal.SIGINT)]
            assert callable(callback)

            callback(*args)
            assert shutdown_event.is_set()
            assert output == ["\nShutting down... Press Ctrl+C again to force."]
            assert not task.done()

            callback(*args)
            await asyncio.sleep(0)
            assert task.cancelled()
        finally:
            restore()
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        assert int(signal.SIGINT) in loop.removed
        assert int(signal.SIGTERM) in loop.removed

    asyncio.run(_run())


@pytest.mark.asyncio
@pytest.mark.parametrize("signal_name", ["SIGINT", "SIGBREAK"])
async def test_gateway_signal_fallback_requests_shutdown_then_forces_and_restores(
    monkeypatch, signal_name: str,
) -> None:
    sigbreak = getattr(signal, "SIGBREAK", 21)
    monkeypatch.setattr(signal, "SIGBREAK", sigbreak, raising=False)
    previous = object()
    handlers = {}
    monkeypatch.setattr(signal, "getsignal", lambda _signum: previous)
    monkeypatch.setattr(signal, "signal", lambda signum, handler: handlers.update({signum: handler}))
    loop = MagicMock()
    loop.add_signal_handler.side_effect = NotImplementedError
    shutdown_event = asyncio.Event()
    task = asyncio.create_task(asyncio.Event().wait())
    await asyncio.sleep(0)
    tasks: list[asyncio.Task[object]] = []
    output: list[str] = []
    restore = server_shutdown.install_shutdown_handlers(
        loop, shutdown_event, tasks, output.append,
    )
    tasks.append(task)
    signum = getattr(signal, signal_name)
    try:
        handlers[signum](signum, None)
        assert shutdown_event.is_set()
        assert output == ["\nShutting down... Press Ctrl+C again to force."]
        assert not task.done()
        handlers[signum](signum, None)
        await asyncio.sleep(0)
        assert task.cancelled()
    finally:
        restore()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    assert handlers == dict.fromkeys((signal.SIGINT, signal.SIGTERM, sigbreak), previous)


def test_commit_dream_changes_skips_noop_run(tmp_path) -> None:
    store = MemoryStore(tmp_path)
    store.write_soul("# Soul")
    store.write_memory("# Memory")
    store.git.init()
    store.git.auto_commit("initial")
    store.git.auto_commit = MagicMock(wraps=store.git.auto_commit)

    assert commit_dream_changes(store, "dream: periodic memory consolidation") is None
    store.git.auto_commit.assert_not_called()


def test_commit_dream_changes_commits_real_edits(tmp_path) -> None:
    store = MemoryStore(tmp_path)
    store.write_soul("# Soul")
    store.write_memory("# Memory")
    store.git.init()
    store.git.auto_commit("initial")
    store.write_memory("# Memory\n- Research notes")
    store.git.auto_commit = MagicMock(wraps=store.git.auto_commit)

    sha = commit_dream_changes(store, "dream: periodic memory consolidation")

    assert sha is not None
    store.git.auto_commit.assert_called_once()
    message = store.git.auto_commit.call_args.args[0]
    assert message.startswith("dream: periodic memory consolidation\n\n")
    assert "Research notes" in message


def test_config_matches_github_copilot_codex_with_hyphen_prefix():
    config = Config()
    config.agents.defaults.model = "github-copilot/gpt-5.3-codex"

    assert config.get_provider_name() == "github_copilot"


def test_config_matches_openai_codex_with_hyphen_prefix():
    config = Config()
    config.agents.defaults.model = "openai-codex/gpt-5.6-sol"

    assert config.get_provider_name() == "openai_codex"


def test_config_dump_excludes_oauth_provider_blocks():
    config = Config()

    providers = config.model_dump(by_alias=True)["providers"]

    assert "openaiCodex" not in providers
    assert "xaiGrok" not in providers
    assert "githubCopilot" not in providers



def test_config_matches_explicit_ollama_prefix_without_api_key():
    config = Config()
    config.agents.defaults.model = "ollama/llama3.2"

    assert config.get_provider_name() == "ollama"
    assert config.get_api_base() == "http://localhost:11434/v1"


def test_config_explicit_ollama_provider_uses_default_localhost_api_base():
    config = Config()
    config.agents.defaults.provider = "ollama"
    config.agents.defaults.model = "llama3.2"

    assert config.get_provider_name() == "ollama"
    assert config.get_api_base() == "http://localhost:11434/v1"


def test_config_accepts_camel_case_explicit_provider_name_for_coding_plan():
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "provider": "volcengineCodingPlan",
                    "model": "doubao-1-5-pro",
                }
            },
            "providers": {
                "volcengineCodingPlan": {
                    "apiKey": "test-key",
                }
            },
        }
    )

    assert config.get_provider_name() == "volcengine_coding_plan"
    assert config.get_api_base() == "https://ark.cn-beijing.volces.com/api/coding/v3"


@pytest.mark.parametrize(
    "provider_name, api_base, config_key",
    [
        pytest.param(
            "lm_studio",
            "http://localhost:1234/v1",
            "lmStudio",
            id="lm_studio_without_api_key_and_uses_default_localhost_api_base",
        ),
        pytest.param(
            "atomic_chat",
            "http://localhost:1337/v1",
            "atomicChat",
            id="atomic_chat_without_api_key_and_uses_default_localhost_api_base",
        ),
    ],
)
def test_local_provider_defaults_without_api_key(provider_name, api_base, config_key):
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "provider": provider_name,
                    "model": "local-model",
                }
            },
            "providers": {
                config_key: {
                    "apiKey": None,
                }
            },
        }
    )

    assert config.get_provider_name() == provider_name
    assert config.get_api_key() is None
    assert config.get_api_base() == api_base


def test_find_by_name_accepts_camel_case_and_hyphen_aliases():
    assert find_by_name("volcengineCodingPlan") is not None
    assert find_by_name("volcengineCodingPlan").name == "volcengine_coding_plan"
    assert find_by_name("github-copilot") is not None
    assert find_by_name("github-copilot").name == "github_copilot"
    assert find_by_name("longcat") is not None
    assert find_by_name("longcat").name == "longcat"
    assert find_by_name("atomic-chat") is not None
    assert find_by_name("atomic-chat").name == "atomic_chat"


def test_config_explicit_longcat_provider_resolves_provider_name():
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "provider": "longcat",
                    "model": "LongCat-Flash-Chat",
                }
            },
            "providers": {
                "longcat": {
                    "apiKey": "test-key",
                }
            },
        }
    )

    assert config.get_provider_name() == "longcat"
    assert config.get_api_base() == "https://api.longcat.chat/openai/v1"


def test_config_auto_detects_longcat_from_model_keyword():
    config = Config.model_validate(
        {
            "agents": {"defaults": {"provider": "auto", "model": "longcat/LongCat-Flash-Chat"}},
            "providers": {"longcat": {"apiKey": "test-key"}},
        }
    )

    assert config.get_provider_name() == "longcat"


def test_config_explicit_xiaomi_mimo_provider_uses_default_api_base():
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "provider": "xiaomi_mimo",
                    "model": "MiniMax-M1-80k",
                }
            },
            "providers": {
                "xiaomiMimo": {
                    "apiKey": "test-key",
                }
            },
        }
    )

    assert config.get_provider_name() == "xiaomi_mimo"
    assert config.get_api_base() == "https://api.xiaomimimo.com/v1"


def test_config_auto_detects_xiaomi_mimo_from_model_keyword():
    config = Config.model_validate(
        {
            "agents": {"defaults": {"provider": "auto", "model": "mimo/MiniMax-M1-80k"}},
            "providers": {"xiaomiMimo": {"apiKey": "test-key"}},
        }
    )

    assert config.get_provider_name() == "xiaomi_mimo"
    assert config.get_api_base() == "https://api.xiaomimimo.com/v1"


def test_config_explicit_minimax_anthropic_provider_uses_default_api_base():
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "provider": "minimax_anthropic",
                    "model": "MiniMax-M2.7-highspeed",
                }
            },
            "providers": {
                "minimaxAnthropic": {
                    "apiKey": "test-key",
                }
            },
        }
    )

    assert config.get_provider_name() == "minimax_anthropic"
    assert config.get_api_key() == "test-key"
    assert config.get_api_base() == "https://api.minimax.io/anthropic"


def test_config_auto_detects_ollama_from_local_api_base():
    config = Config.model_validate(
        {
            "agents": {"defaults": {"provider": "auto", "model": "llama3.2"}},
            "providers": {"ollama": {"apiBase": "http://localhost:11434/v1"}},
        }
    )

    assert config.get_provider_name() == "ollama"
    assert config.get_api_base() == "http://localhost:11434/v1"


def test_config_prefers_ollama_over_vllm_when_both_local_providers_configured():
    config = Config.model_validate(
        {
            "agents": {"defaults": {"provider": "auto", "model": "llama3.2"}},
            "providers": {
                "vllm": {"apiBase": "http://localhost:8000"},
                "ollama": {"apiBase": "http://localhost:11434/v1"},
            },
        }
    )

    assert config.get_provider_name() == "ollama"
    assert config.get_api_base() == "http://localhost:11434/v1"


def test_config_falls_back_to_vllm_when_ollama_not_configured():
    config = Config.model_validate(
        {
            "agents": {"defaults": {"provider": "auto", "model": "llama3.2"}},
            "providers": {
                "vllm": {"apiBase": "http://localhost:8000"},
            },
        }
    )

    assert config.get_provider_name() == "vllm"
    assert config.get_api_base() == "http://localhost:8000"


def test_config_cloud_nemotron_is_not_hijacked_by_unconfigured_ollama():
    """`nvidia/nemotron-*` via a gateway must not route to Ollama when no
    Ollama endpoint is configured. Ollama keeps "nemotron" in its keywords
    for bare-model auto-routing (PR #1863), which previously hijacked
    cloud-hosted nemotron variants and silently sent traffic to
    http://localhost:11434/v1."""
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "provider": "auto",
                    "model": "nvidia/nemotron-3-super-120b-a12b",
                }
            },
            "providers": {"openrouter": {"apiKey": "sk-or-test"}},
        }
    )

    assert config.get_provider_name() == "openrouter"
    assert config.get_api_base() == "https://openrouter.ai/api/v1"


def test_config_bare_nemotron_still_auto_routes_to_configured_ollama():
    """Preserves PR #1863 intent: when the user has actually configured an
    Ollama endpoint, a bare nemotron model still auto-routes there."""
    config = Config.model_validate(
        {
            "agents": {"defaults": {"provider": "auto", "model": "nemotron-3-nano"}},
            "providers": {"ollama": {"apiBase": "http://localhost:11434/v1"}},
        }
    )

    assert config.get_provider_name() == "ollama"
    assert config.get_api_base() == "http://localhost:11434/v1"


def test_config_cloud_nemotron_is_not_hijacked_by_configured_ollama():
    """An explicit cloud namespace takes precedence over local keywords."""
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "provider": "auto",
                    "model": "nvidia/nemotron-3-super-120b-a12b",
                }
            },
            "providers": {
                "ollama": {"apiBase": "http://localhost:11434/v1"},
                "openrouter": {"apiKey": "sk-or-test"},
            },
        }
    )

    assert config.get_provider_name() == "openrouter"
    assert config.get_api_base() == "https://openrouter.ai/api/v1"


def test_openai_compat_provider_passes_model_through():
    from cirno_core.providers.openai_compat_provider import OpenAICompatProvider

    with patch("cirno_core.providers.openai_compat_provider.AsyncOpenAI"):
        provider = OpenAICompatProvider(default_model="github-copilot/gpt-5.3-codex")

    assert provider.get_default_model() == "github-copilot/gpt-5.3-codex"


def test_openai_codex_proxy_config_affects_provider_and_signature():
    def config_with_proxy(proxy: str) -> Config:
        return Config.model_validate(
            {
                "agents": {
                    "defaults": {
                        "provider": "openai-codex",
                        "model": "openai-codex/gpt-5.5",
                    }
                },
                "network": {"proxy": proxy},
                "providers": {"openaiCodex": {"useProxy": True}},
            }
        )

    proxy = "http://127.0.0.1:23458"
    config = config_with_proxy(proxy)

    provider = make_provider(config)

    assert provider.__class__.__name__ == "OpenAICodexProvider"
    assert provider.proxy == proxy
    assert provider_signature(config) != provider_signature(
        config_with_proxy("http://127.0.0.1:23459")
    )


def test_provider_proxy_rejects_unsupported_backend():
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "provider": "azure_openai",
                    "model": "gpt-4.1",
                }
            },
            "providers": {
                "azureOpenai": {
                    "apiKey": "sk-test",
                    "apiBase": "https://azure.example/openai/v1",
                    "useProxy": True,
                }
            },
        }
    )

    with pytest.raises(ValueError, match=r"providers\.azure_openai\.use_proxy"):
        make_provider(config)


def test_github_copilot_provider_strips_prefixed_model_name():
    from cirno_core.providers.github_copilot_provider import GitHubCopilotProvider

    with patch("cirno_core.providers.openai_compat_provider.AsyncOpenAI"):
        provider = GitHubCopilotProvider(default_model="github-copilot/gpt-5.1")

    kwargs = provider._build_kwargs(
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        model="github-copilot/gpt-5.1",
        max_tokens=16,
        temperature=0.1,
        reasoning_effort=None,
        tool_choice=None,
    )

    assert kwargs["model"] == "gpt-5.1"


@pytest.mark.asyncio
async def test_github_copilot_provider_refreshes_client_api_key_before_chat():
    from cirno_core.providers.github_copilot_provider import GitHubCopilotProvider

    mock_client = MagicMock()
    mock_client.api_key = "no-key"
    mock_client.chat.completions.create = AsyncMock(return_value={
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    })

    with patch("cirno_core.providers.openai_compat_provider.AsyncOpenAI", return_value=mock_client):
        provider = GitHubCopilotProvider(default_model="github-copilot/gpt-4")
        await provider._ensure_client()

    provider._get_copilot_access_token = AsyncMock(return_value="copilot-access-token")

    response = await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        model="github-copilot/gpt-4",
        max_tokens=16,
        temperature=0.1,
    )

    assert response.content == "ok"
    assert provider._client.api_key == "copilot-access-token"
    provider._get_copilot_access_token.assert_awaited_once()
    mock_client.chat.completions.create.assert_awaited_once()


def test_openai_codex_strip_prefix_supports_hyphen_and_underscore():
    assert _strip_model_prefix("openai-codex/gpt-5.6-sol") == "gpt-5.6-sol"
    assert _strip_model_prefix("openai_codex/gpt-5.6-sol") == "gpt-5.6-sol"


def test_make_provider_passes_extra_headers_to_custom_provider():
    config = Config.model_validate(
        {
            "agents": {"defaults": {"provider": "custom", "model": "gpt-4o-mini"}},
            "providers": {
                "custom": {
                    "apiKey": "test-key",
                    "apiBase": "https://example.com/v1",
                    "extraHeaders": {
                        "APP-Code": "demo-app",
                        "x-session-affinity": "sticky-session",
                    },
                }
            }
        }
    )

    with patch("cirno_core.providers.openai_compat_provider.AsyncOpenAI") as mock_async_openai:
        provider = make_provider(config)
        asyncio.run(provider._ensure_client())

    kwargs = mock_async_openai.call_args.kwargs
    assert kwargs["api_key"] == "test-key"
    assert kwargs["base_url"] == "https://example.com/v1"
    assert kwargs["default_headers"]["APP-Code"] == "demo-app"
    assert kwargs["default_headers"]["x-session-affinity"] == "sticky-session"


def test_make_provider_treats_dynamic_custom_provider_as_direct():
    config = Config.model_validate(
        {
            "agents": {"defaults": {"provider": "my-company-api", "model": "gpt-4o-mini"}},
            "providers": {
                "my-company-api": {
                    "apiBase": "https://example.com/v1",
                }
            },
        }
    )

    with patch("cirno_core.providers.openai_compat_provider.AsyncOpenAI") as mock_async_openai:
        provider = make_provider(config)
        asyncio.run(provider._ensure_client())

    assert provider.get_default_model() == "gpt-4o-mini"
    assert provider._spec.name == "my_company_api"
    assert provider._spec.is_direct is True
    kwargs = mock_async_openai.call_args.kwargs
    assert kwargs["api_key"] == "no-key"
    assert kwargs["base_url"] == "https://example.com/v1"


def test_make_provider_strips_dynamic_custom_route_prefix_from_request_model():
    config = Config.model_validate(
        {
            "agents": {"defaults": {"provider": "auto", "model": "my-company-api/gpt-4o-mini"}},
            "providers": {
                "my-company-api": {
                    "apiBase": "https://example.com/v1",
                }
            },
        }
    )

    provider = make_provider(config)

    kwargs = provider._build_kwargs(
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        model=None,
        max_tokens=16,
        temperature=0.1,
        reasoning_effort=None,
        tool_choice=None,
    )
    body = provider._build_responses_body(
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        model=None,
        max_tokens=16,
        temperature=0.1,
        reasoning_effort=None,
        tool_choice=None,
    )

    assert config.get_provider_name() == "my-company-api"
    assert kwargs["model"] == "gpt-4o-mini"
    assert body["model"] == "gpt-4o-mini"


@pytest.mark.parametrize(
    "provider_name, model",
    [
        pytest.param(
            "my-company-api",
            "openai/gpt-4o-mini",
            id="preserves_namespaced_model_for_forced_dynamic_provider",
        ),
        pytest.param(
            "auto",
            "my-company-api/openai/gpt-4o-mini",
            id="strips_dynamic_custom_route_prefix_once",
        ),
    ],
)
def test_make_provider_preserves_dynamic_provider_model_namespace(provider_name, model):
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "provider": provider_name,
                    "model": model,
                }
            },
            "providers": {
                "my-company-api": {
                    "apiBase": "https://example.com/v1",
                }
            },
        }
    )

    provider = make_provider(config)
    kwargs = provider._build_kwargs(
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        model=None,
        max_tokens=16,
        temperature=0.1,
        reasoning_effort=None,
        tool_choice=None,
    )

    assert kwargs["model"] == "openai/gpt-4o-mini"


def test_make_provider_rejects_dynamic_custom_provider_without_api_base():
    config = Config.model_validate(
        {
            "agents": {"defaults": {"provider": "my-company-api", "model": "gpt-4o-mini"}},
            "providers": {
                "my-company-api": {
                    "apiKey": "sk-test",
                }
            },
        }
    )

    with pytest.raises(ValueError, match="Provider 'my-company-api' requires api_base"):
        make_provider(config)


def test_make_provider_rejects_auto_dynamic_custom_prefix_without_api_base():
    config = Config.model_validate(
        {
            "agents": {"defaults": {"provider": "auto", "model": "companyProxy/gpt-4o"}},
            "providers": {
                "otherProxy": {
                    "apiBase": "https://other.example.test/v1",
                },
                "companyProxy": {
                    "apiKey": "sk-company",
                },
            },
        }
    )

    with pytest.raises(ValueError, match="Provider 'companyProxy' requires api_base"):
        make_provider(config)


@pytest.mark.parametrize(
    "content, expected",
    [
        ("", False),
        ("# Title\n\n## Active Tasks\n", False),
        ("<!--\nmulti-line\ncomment\n-->\n", False),  # block comment, not tasks
        ("<!-- single line -->\n", False),
        ("## Active Tasks\n\n- water the plants\n", True),
        ("## Active Tasks\n\n### Garden\n\n- water the plants\n", True),
        ("## Notes\n\nsome random note\n", False),
        ("stray text before any heading\n## Active Tasks\n\n- task\n", True),
        ("stray text before any heading\n", False),
    ],
)
def test_heartbeat_has_active_tasks(content, expected):
    from cirno_core.runtime.heartbeat import has_active_tasks

    assert has_active_tasks(content) is expected


def test_heartbeat_skips_bundled_template():
    from cirno_core.runtime.heartbeat import has_active_tasks
    from cirno_core.utils.home_templates import load_bundled_template

    assert has_active_tasks(load_bundled_template("HEARTBEAT.md")) is False


def test_launch_browser_uses_macos_url_services(monkeypatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(cli_webui_support.sys, "platform", "darwin")
    monkeypatch.setattr(
        cli_webui_support,
        "_launch_macos_browser",
        lambda url: seen.append(url) or True,
    )

    assert cli_webui_support._launch_browser("http://127.0.0.1:8765/") is True
    assert seen == ["http://127.0.0.1:8765/"]


def test_launch_browser_uses_unix_launcher_on_linux(monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(cli_webui_support.sys, "platform", "linux")
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.setattr(
        cli_webui_support,
        "_launch_unix_browser",
        lambda url: opened.append(url) or True,
    )

    assert cli_webui_support._launch_browser("http://127.0.0.1:8765/") is True
    assert opened == ["http://127.0.0.1:8765/"]
