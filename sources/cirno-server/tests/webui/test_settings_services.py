from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cirno_server.channels.websocket.config import WebSocketConfig
from cirno_server.webui.services import build_server_services
from cirno_server.webui.settings.services import (
    WebUIOAuthFlowRegistry,
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
    return build_server_services(
        config=WebSocketConfig(),
        bus=MagicMock(),
        session_manager=None,
        static_dist_path=None,
        workspace_path=workspace,
        default_restrict_to_workspace=False,
        config_path=config_path,
        runtime_model_name=None,


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


def test_gateway_uses_saved_upload_limits_and_reserves_capacity_for_a_whole_batch(tmp_path):
    from cirno_core.config.loader import save_config
    from cirno_core.config.schema import Config
    from cirno_server.webui.settings.api import update_runtime_config_settings

    path = tmp_path / "instance/config.json"
    path.parent.mkdir()
    save_config(Config(), path)
    values = {"server.uploads.max_file_mb": 150, "server.uploads.max_video_mb": 200,
              "server.uploads.max_total_mb": 600}
    payload = update_runtime_config_settings(values, config_path=path)
    assert payload["requires_restart"]
    assert all(payload["runtime_config"][key] == value for key, value in values.items())
    gateway = _gateway(path, tmp_path / "workspace")
    limits = gateway.ingress.bootstrap_limits(max_frame_bytes=1048576)["attachments"]
    assert limits["max_file_bytes"] == 150 * 1024 * 1024
    assert limits["max_video_bytes"] == 200 * 1024 * 1024
    assert limits["max_total_bytes"] == 600 * 1024 * 1024
    assert gateway.uploads.store.limits is gateway.ingress.attachments
    assert gateway.uploads.store.max_pending_bytes >= 800 * 1024 * 1024


@pytest.mark.parametrize("value", [0, -1, True, "200", 1.5])
def test_invalid_upload_settings_preserve_configuration(tmp_path, value):
    from cirno_core.config.loader import save_config
    from cirno_core.config.schema import Config
    from cirno_server.webui.settings.api import update_runtime_config_settings
    from cirno_server.webui.settings.contracts import WebUISettingsError

    path = tmp_path / "config.json"
    save_config(Config(), path)
    before = path.read_bytes()
    with pytest.raises(WebUISettingsError):
        update_runtime_config_settings({"server.uploads.max_file_mb": value}, config_path=path)
    assert path.read_bytes() == before
