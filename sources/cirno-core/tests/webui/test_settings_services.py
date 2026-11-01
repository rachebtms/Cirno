from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cirno.channels.websocket.runtime import WebSocketConfig
from cirno.config.loader import load_config, save_config
from cirno.config.schema import Config
from cirno.webui.gateway_services import build_gateway_services
from cirno.webui.settings.api import settings_payload, update_agent_settings
from cirno.webui.settings.services import (
    WebUIOAuthFlowRegistry,
    WebUISettingsServices,
)


class _Flow:
    has_pending_work = False

    def __init__(self, *, expired: bool = False) -> None:
        self.expired = expired
        self.cancel_count = 0

    def cancel(self) -> None:
        self.cancel_count += 1

    def wait_closed(self) -> None:
        pass

    def complete(self, response=None):
        return None


def _gateway(config_path: Path, workspace: Path):
    return build_gateway_services(
        config=WebSocketConfig(),
        bus=MagicMock(),
        session_manager=None,
        static_dist_path=None,
        workspace_path=workspace,
        default_restrict_to_workspace=False,
        config_path=config_path,
        runtime_model_name=None,
        runtime_surface="browser",
        runtime_capabilities_overrides=None,
    )










def test_oauth_registry_preserves_expiry_capacity_completion_and_cancel() -> None:
    registry = WebUIOAuthFlowRegistry(max_flows=2)
    expired = _Flow(expired=True)
    oldest = _Flow()
    newest = _Flow()
    replacement = _Flow()

    registry.register("openai_codex", "expired", expired)
    registry.register("openai_codex", "oldest", oldest)
    assert expired.cancel_count == 1
    assert registry.get("openai_codex", "expired") is None

    registry.register("xai_grok", "newest", newest)
    registry.register("openai_codex", "replacement", replacement)
    assert oldest.cancel_count == 1
    assert registry.get("openai_codex", "oldest") is None
    assert registry.get("xai_grok", "newest") is newest
    assert registry.get("openai_codex", "newest") is None

    registry.remove("xai_grok", "newest", newest, cancel=False)
    assert newest.cancel_count == 0
    assert registry.get("xai_grok", "newest") is None

    registry.clear("openai_codex")
    assert replacement.cancel_count == 1
    assert registry.get("openai_codex", "replacement") is None


def test_oauth_registry_capacity_counts_cancelled_workers_until_exit():
    release = threading.Event()
    cancelled = threading.Event()

    class ThreadFlow(_Flow):
        def __init__(self):
            super().__init__()
            self.thread = threading.Thread(target=lambda: release.wait(3))

        @property
        def has_pending_work(self):
            return self.thread.is_alive()

        def cancel(self):
            cancelled.set()

        def wait_closed(self):
            self.thread.join()

    registry = WebUIOAuthFlowRegistry(max_flows=1)
    flow = ThreadFlow()
    registry.register("github_copilot", "first", flow)
    flow.thread.start()
    replacement = _Flow()
    try:
        with pytest.raises(RuntimeError, match="still stopping"):
            registry.register("github_copilot", "next", replacement)
        assert cancelled.is_set()
        assert registry.get("github_copilot", "first") is None
        assert registry.get("github_copilot", "next") is None
        assert registry.has_pending_work
    finally:
        release.set()
        flow.wait_closed()
    assert not registry.has_pending_work
    registry.register("github_copilot", "next", replacement)
    registry.close()
    with pytest.raises(RuntimeError, match="closing"):
        registry.register("github_copilot", "after-close", _Flow())


def test_oauth_registry_keeps_flow_that_starts_while_cancellation_is_pending():
    cancelling, allow_cancel, release_worker = (threading.Event() for _ in range(3))

    class StartingFlow(_Flow):
        def __init__(self):
            super().__init__()
            self.thread = threading.Thread(target=lambda: release_worker.wait(3))

        @property
        def has_pending_work(self):
            return self.thread.is_alive()

        def cancel(self):
            cancelling.set()
            assert allow_cancel.wait(3)

        def wait_closed(self):
            if self.thread.ident is not None:
                self.thread.join()

    registry = WebUIOAuthFlowRegistry(max_flows=2)
    flow = StartingFlow()
    registry.register("github_copilot", "starting", flow)
    removal = threading.Thread(target=lambda: registry.remove("github_copilot", "starting", flow))
    removal.start()
    try:
        assert cancelling.wait(1)
        # Another request can register between register/start in the first login,
        # while its cancellation is waiting for the provider's commit lock.
        registry.register("xai_grok", "another", _Flow())
        flow.thread.start()
        allow_cancel.set()
        removal.join(timeout=1)
        assert not removal.is_alive()
        assert registry.has_pending_work
    finally:
        allow_cancel.set()
        release_worker.set()
        removal.join(timeout=2)
        flow.wait_closed()
        registry.close()
