import asyncio
import json
import re
import shutil
import signal
import urllib.error
from contextlib import contextmanager, suppress
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cirno_core.agent.subagents.manager import SubagentManager
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.bus.events import InboundMessage, OutboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.config.schema import Config
from cirno_core.cron.webui_metadata import cron_proactive_delivery_metadata
from cirno_core.memory.consolidation import MemoryStore
from cirno_core.providers.factory import ProviderSnapshot, make_provider, provider_signature
from cirno_core.providers.openai_codex_provider import _strip_model_prefix
from cirno_core.providers.registry import find_by_name
from cirno_core.session.transport_metadata import (
    WEBUI_MESSAGE_SOURCE_METADATA_KEY,
    WEBUI_TURN_METADATA_KEY,
)
from cirno_server import application as cli_gateway_runtime
from cirno_server.cli import webui_support as cli_webui_support
from cirno_server.webui.dev import WebUIDevError
from typer.testing import CliRunner

runner = CliRunner()




def _without_rendered_line_breaks(output: str) -> str:
    return "".join(output.splitlines())


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


def _fake_provider():
    """Return a minimal fake provider that satisfies AgentLoop.__init__."""
    p = MagicMock(aclose=AsyncMock())
    p.generation.max_tokens = 4096
    return p


class _StopServerError(RuntimeError):
    pass


class _ServerAgentContractStub:
    """Minimal stable AgentLoop surface required by gateway assembly tests."""

    tools = ToolRegistry()

    async def estimate_session_context_usage(self, *_args, **_kwargs):
        return None
    subagents = MagicMock(spec=SubagentManager)

    @contextmanager
    def maintenance(self):
        yield

    async def discard_session(self, _session_key: str) -> None:
        pass

    @staticmethod
    def mcp_runtime_status() -> dict[str, str]:
        return {}

    @staticmethod
    def pending_cron_job_ids_for_session(_session_key: str) -> set[str]:
        return set()

    @staticmethod
    def pending_local_trigger_ids_for_session(_session_key: str) -> set[str]:
        return set()

    async def submit_local_trigger_turn(
        self,
        _msg: InboundMessage,
    ) -> OutboundMessage | None:
        return None

    def preserve_inflight_turns_on_shutdown(self) -> None:
        return None


class _EmptyServerSessionManager:
    """Minimal session-manager contract for gateway assembly tests."""

    def list_sessions(self) -> list[dict[str, object]]:
        return []

    def list_session_metadata(self) -> list[dict[str, object]]:
        return []

    @property
    def state(self):
        return SimpleNamespace(
            list_sessions=AsyncMock(return_value=[]),
            migrate_history=AsyncMock(),
            record_delivery=AsyncMock(),
            aclose=AsyncMock(),
        )


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
        restore = cli_gateway_runtime._install_gateway_shutdown_handlers(
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
    restore = cli_gateway_runtime._install_gateway_shutdown_handlers(
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


def test_disabled_dream_cursor_only_advances_when_behind(tmp_path) -> None:
    store = MemoryStore(tmp_path)
    store.append_history("first")
    store.append_history("second")

    cli_gateway_runtime._advance_dream_cursor_if_behind(store)
    assert store.get_last_dream_cursor() == 2

    store.set_last_dream_cursor(10)
    cli_gateway_runtime._advance_dream_cursor_if_behind(store)
    assert store.get_last_dream_cursor() == 10


def test_commit_dream_changes_skips_noop_run(tmp_path) -> None:
    store = MemoryStore(tmp_path)
    store.write_soul("# Soul")
    store.write_memory("# Memory")
    store.git.init()
    store.git.auto_commit("initial")
    store.git.auto_commit = MagicMock(wraps=store.git.auto_commit)

    assert cli_gateway_runtime._commit_dream_changes(store) is None
    store.git.auto_commit.assert_not_called()


def test_commit_dream_changes_commits_real_edits(tmp_path) -> None:
    store = MemoryStore(tmp_path)
    store.write_soul("# Soul")
    store.write_memory("# Memory")
    store.git.init()
    store.git.auto_commit("initial")
    store.write_memory("# Memory\n- Research notes")
    store.git.auto_commit = MagicMock(wraps=store.git.auto_commit)

    sha = cli_gateway_runtime._commit_dream_changes(store)

    assert sha is not None
    store.git.auto_commit.assert_called_once()
    message = store.git.auto_commit.call_args.args[0]
    assert message.startswith("dream: periodic memory consolidation\n\n")
    assert "Research notes" in message


@pytest.fixture
def mock_paths():
    """Mock config/workspace paths for test isolation."""
    from importlib import import_module

    import_module("cirno_server.channels.validation")
    with patch("cirno_core.config.loader.get_config_path") as mock_cp, \
         patch("cirno_core.config.loader.save_config") as mock_sc, \
         patch("cirno_core.config.loader.load_config") as mock_lc, \
         patch("cirno_server.cli.commands.get_workspace_path") as mock_ws:
        base_dir = Path("./test_onboard_data")
        if base_dir.exists():
            shutil.rmtree(base_dir)
        base_dir.mkdir()

        config_file = base_dir / "config.json"
        workspace_dir = base_dir / "workspace"

        mock_cp.return_value = config_file
        mock_ws.return_value = workspace_dir
        mock_lc.side_effect = lambda _config_path=None: Config()

        def _save_config(config: Config, config_path: Path | None = None):
            target = config_path or config_file
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(config.model_dump(by_alias=True)), encoding="utf-8")

        mock_sc.side_effect = _save_config

        yield config_file, workspace_dir, mock_ws

        if base_dir.exists():
            shutil.rmtree(base_dir)










def _strip_ansi(text):
    """Remove ANSI escape codes from text."""
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_escape.sub('', text)










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


















def test_provider_logout_paths_resolve_to_expected_files():
    from cirno_core.providers.github_copilot_provider import get_storage
    from cirno_core.providers.xai_oauth import get_xai_oauth_storage_path
    from oauth_cli_kit.providers import OPENAI_CODEX_PROVIDER
    from oauth_cli_kit.storage import FileTokenStorage

    codex_storage = FileTokenStorage(token_filename=OPENAI_CODEX_PROVIDER.token_filename)
    codex_path = codex_storage.get_token_path()
    assert codex_path.name == "codex.json"
    assert codex_path.parent.name == "auth"

    xai_path = get_xai_oauth_storage_path()
    assert xai_path.name == "xai.json"
    assert xai_path.parent.name == "auth"

    gh_storage = get_storage()
    gh_path = gh_storage.get_token_path()
    assert gh_path.name == "github-copilot.json"
    assert gh_path.parent.name == "auth"






















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
    from cirno_server.application import _heartbeat_has_active_tasks

    assert _heartbeat_has_active_tasks(content) is expected


def test_heartbeat_skips_bundled_template():
    from cirno_core.utils.helpers import load_bundled_template
    from cirno_server.application import _heartbeat_has_active_tasks

    assert _heartbeat_has_active_tasks(load_bundled_template("HEARTBEAT.md")) is False


def _write_instance_config(tmp_path: Path) -> Path:
    config_file = tmp_path / "instance" / "config.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("{}")
    return config_file


def _stop_gateway_provider(_config) -> object:
    raise _StopServerError("stop")


def _test_provider_snapshot(provider: object, config: Config) -> ProviderSnapshot:
    return ProviderSnapshot(
        provider=provider,
        model=config.agents.defaults.model,
        context_window_tokens=config.agents.defaults.context_window_tokens,
        signature=("test",),
    )


def _patch_webui_provider_ready(monkeypatch) -> None:
    monkeypatch.setattr(
        "cirno_core.providers.factory.validate_provider_setup",
        lambda _config: None,
    )


def _patch_gateway_ports_free(monkeypatch) -> None:
    monkeypatch.setattr("cirno_server.cli.webui._gateway_health_ready", lambda *_a, **_kw: False)
    monkeypatch.setattr("cirno_server.cli.webui._tcp_endpoint_reachable", lambda *_a, **_kw: False)
    monkeypatch.setattr("cirno_server.cli.webui._webui_endpoint_reachable", lambda *_a, **_kw: False)
    monkeypatch.setattr(
        "cirno_server.application._tcp_endpoint_reachable",
        lambda *_a, **_kw: False,
    )
    monkeypatch.setattr(
        "cirno_server.application._webui_endpoint_reachable",
        lambda *_a, **_kw: False,
    )


def _record_gateway_lease_release(monkeypatch, captured: dict[str, object]) -> None:
    from cirno_server.lifecycle import ServerClientLease

    original_release = ServerClientLease.release

    def record_release(
        lease: ServerClientLease,
        *,
        timeout_s: int = 20,
        wait_for_stop: bool = True,
    ) -> bool:
        captured["lease_release_wait_for_stop"] = wait_for_stop
        captured["dev_running_at_release"] = captured.get("dev_running")
        return original_release(
            lease,
            timeout_s=timeout_s,
            wait_for_stop=wait_for_stop,
        )

    monkeypatch.setattr(ServerClientLease, "release", record_release)


def _patch_webui_managed_gateway(
    monkeypatch,
    seen: dict[str, object] | None = None,
) -> dict[str, object]:
    """Run WebUI CLI tests against a managed gateway without spawning a process."""
    from cirno_server.lifecycle import RuntimeResult, ServerStatus

    captured = seen if seen is not None else {}
    _record_gateway_lease_release(monkeypatch, captured)

    class _FakeRuntime:
        def __init__(self, **kwargs) -> None:
            captured["runtime_kwargs"] = kwargs
            self.paths = kwargs["paths"]
            self.running = False

        def start_background(self, options):
            captured["start_options"] = options
            self.running = True
            status = ServerStatus(
                running=True,
                pid=123,
                state_path=Path("gateway.json"),
                log_path=Path("gateway.log"),
                port=options.port,
                reason="running",
            )
            return RuntimeResult(True, "server_started_background", status)

        def start_on_demand(self, options):
            from cirno_server.lifecycle import ServerClientLease

            ServerClientLease(self, kind="test-webui").mark_ephemeral()
            return self.start_background(options)

        def status(self):
            return SimpleNamespace(running=self.running)

        def stop(self, *, timeout_s: int):
            captured["stop_timeout"] = timeout_s
            self.running = False
            return RuntimeResult(True, "server_stopped", self.status())

        _stop = stop

    monkeypatch.setattr("cirno_server.lifecycle.ServerRuntime", _FakeRuntime)
    monkeypatch.setattr(
        "cirno_server.cli.webui._prepare_webui_bundle_for_gateway",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "cirno_server.cli.webui._attach_to_background_gateway",
        lambda runtime, **_kwargs: captured.__setitem__("attached_runtime", runtime),
    )
    monkeypatch.setattr("cirno_server.cli.webui._wait_for_webui", lambda *_args, **_kwargs: True)
    return captured


def _patch_cli_command_runtime(
    monkeypatch,
    config: Config,
    *,
    set_config_path=None,
    sync_templates=None,
    make_provider=None,
    message_bus=None,
    session_manager=None,
    cron_service=None,
    get_cron_dir=None,
) -> None:
    from importlib import import_module

    # Load adapter contracts before replacing runtime factories for this invocation.
    import_module("cirno_core.session.webui_turns")
    import_module("cirno_server.channels.validation")
    import_module("cirno_server.channels.websocket.runtime")
    provider_factory = make_provider or (lambda _config: _fake_provider())

    monkeypatch.setattr(
        "cirno_core.config.loader.set_config_path",
        set_config_path or (lambda _path: None),
    )
    monkeypatch.setattr("cirno_core.config.loader.load_config", lambda _path=None: config)
    monkeypatch.setattr("cirno_core.config.loader.resolve_config_env_vars", lambda c: c)
    monkeypatch.setattr(
        "cirno_server.cli.commands.sync_workspace_templates",
        sync_templates or (lambda _path: None),
    )
    monkeypatch.setattr(
        "cirno_server.cli.webui.sync_workspace_templates",
        lambda path, **_kwargs: sync_templates(path) if sync_templates else None,
    )
    monkeypatch.setattr(
        "cirno_server.application.sync_workspace_templates",
        sync_templates or (lambda _path: None),
    )
    monkeypatch.setattr(
        "cirno_core.providers.factory.make_provider",
        provider_factory,
    )
    monkeypatch.setattr(
        "cirno_core.providers.factory.build_provider_snapshot",
        lambda _config: _test_provider_snapshot(provider_factory(_config), _config),
    )
    monkeypatch.setattr(
        "cirno_core.providers.factory.load_provider_snapshot",
        lambda _config_path=None: _test_provider_snapshot(provider_factory(config), config),
    )
    monkeypatch.setattr(
        "cirno_server.cli.webui_support._provider_setup_error",
        lambda _config: None,
    )
    _patch_gateway_ports_free(monkeypatch)

    if message_bus is not None:
        monkeypatch.setattr("cirno_core.bus.queue.MessageBus", message_bus)
    if session_manager is not None:
        monkeypatch.setattr("cirno_core.session.manager.SessionManager", session_manager)
    if cron_service is not None:
        monkeypatch.setattr("cirno_core.cron.service.CronService", cron_service)
    if get_cron_dir is not None:
        monkeypatch.setattr("cirno_core.config.paths.get_cron_dir", get_cron_dir)














async def test_webui_dev_monitor_fails_when_sidecar_exits() -> None:
    dev_server = MagicMock()
    dev_server.ensure_running.side_effect = WebUIDevError(
        "WebUI development server exited unexpectedly (code 23)"
    )

    with pytest.raises(WebUIDevError, match=r"exited unexpectedly \(code 23\)"):
        await cli_gateway_runtime._watch_webui_dev_server(
            dev_server,
            asyncio.Event(),
            poll_interval_s=0,
        )


async def test_webui_dev_monitor_ignores_an_expected_gateway_shutdown() -> None:
    dev_server = MagicMock()
    shutdown_event = asyncio.Event()
    shutdown_event.set()

    await cli_gateway_runtime._watch_webui_dev_server(
        dev_server,
        shutdown_event,
        poll_interval_s=0,
    )

    dev_server.ensure_running.assert_not_called()


def test_browser_readiness_accepts_http_auth_response(monkeypatch) -> None:
    def auth_required(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "http://127.0.0.1:8765/webui/bootstrap",
            401,
            "authentication required",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("urllib.request.urlopen", auth_required)

    assert cli_gateway_runtime._http_endpoint_responding(
        "http://127.0.0.1:8765/webui/bootstrap"
    ) is True


def test_browser_readiness_rejects_connection_error(monkeypatch) -> None:
    def unavailable(*_args, **_kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", unavailable)

    assert cli_gateway_runtime._http_endpoint_responding(
        "http://127.0.0.1:8765/webui/bootstrap"
    ) is False
















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


























def _patch_serve_runtime(monkeypatch, config: Config, seen: dict[str, object]) -> None:
    pytest.importorskip("aiohttp")

    class _FakeApiApp:
        def __init__(self) -> None:
            self.on_startup: list[object] = []
            self.on_cleanup: list[object] = []

    class _FakeAgentLoop:
        @classmethod
        def from_config(cls, config, bus=None, **extra):
            return cls(workspace=config.workspace_path, **extra)
        def __init__(self, **kwargs) -> None:
            seen["workspace"] = kwargs["workspace"]

        async def aclose(self) -> None:
            return None

    def _fake_create_app(
        agent_loop,
        model_name: str,
        request_timeout: float,
        api_key: str = "",
        prepare_agent=None,
    ):
        seen["agent_loop"] = agent_loop
        seen["model_name"] = model_name
        seen["request_timeout"] = request_timeout
        seen["api_key"] = api_key
        seen["prepare_agent"] = prepare_agent
        return _FakeApiApp()

    def _fake_run_app(api_app, host: str, port: int, print):
        seen["api_app"] = api_app
        seen["host"] = host
        seen["port"] = port

    _patch_cli_command_runtime(
        monkeypatch,
        config,
        message_bus=MessageBus,
        session_manager=lambda _workspace: _EmptyServerSessionManager(),
    )
    monkeypatch.setattr("cirno_server.cli.commands.AgentLoop", _FakeAgentLoop)
    monkeypatch.setattr("cirno.api.server.create_app", _fake_create_app)
    monkeypatch.setattr("aiohttp.web.run_app", _fake_run_app)
