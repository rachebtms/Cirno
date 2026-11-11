"""Cross-suite test infrastructure."""

from __future__ import annotations

import os
import ssl
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from threading import Thread
from uuid import uuid4

import certifi
import pytest
from loguru import logger


@pytest.fixture(autouse=True)
def _isolate_tokenizer_warmup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests deterministic and out of the user's tokenizer cache and network."""
    monkeypatch.setattr("cirno_core.utils.token_encoding._encoding", None)
    monkeypatch.setattr("cirno_core.utils.token_encoding._warmup_thread", Thread())


@pytest.fixture(autouse=True)
def _isolate_tool_entry_points(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only load external tool plugins explicitly provided by the test."""
    monkeypatch.setattr("cirno_core.agent.tools.loader.entry_points", lambda **_kwargs: ())


@pytest.fixture(autouse=True)
def _isolate_cirno_log_activation() -> Iterator[None]:
    """Keep CLI log settings from leaking into later tests in the same process."""
    logger.enable("cirno_core")
    logger.enable("cirno_server")
    try:
        yield
    finally:
        logger.enable("cirno_core")
        logger.enable("cirno_server")


@pytest.fixture(autouse=True)
def _isolate_runtime_stores(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Isolate writable stores without making a directory for pure tests."""
    import cirno_core.session.location as session_location
    import cirno_usage.service as llm_usage

    # A sibling of tmp_path stays outside any test's agent workspace. mkdir is
    # deferred until a store is used and remains safe for concurrent callers.
    data_root = tmp_path_factory.getbasetemp() / "runtime-data" / uuid4().hex
    # Memory, Skills and provider credentials now belong to Home too. Tests must
    # not read or write the developer's instance through their default paths.
    monkeypatch.setenv("HOME", str(data_root / "user"))
    monkeypatch.setenv("USERPROFILE", str(data_root / "user"))
    monkeypatch.setattr("cirno_core.config.home._instance_path", None)
    monkeypatch.setattr("cirno_core.config.loader._current_config_path", None)

    def runtime_subdir(name: str) -> Path:
        path = data_root / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr(session_location, "get_runtime_subdir", runtime_subdir)
    stores: dict[Path, llm_usage.LLMUsageStore] = {}
    monkeypatch.setattr(llm_usage, "_STORES", stores)
    try:
        yield
    finally:
        for store in stores.values():
            store.close()


@pytest.fixture(scope="session", autouse=True)
def _use_windows_system_ca_for_default_http_clients() -> Iterator[None]:
    """Avoid reparsing certifi's CA bundle for every offline HTTP client.

    Loading certifi takes roughly 0.7 seconds per client on Windows. The test
    suite constructs hundreds of clients while mocking their I/O. System roots
    preserve certificate verification for accidental local requests; explicit
    ``cafile``, ``capath``, and ``cadata`` arguments still use the real loader.
    """
    if sys.platform != "win32":
        yield
        return

    original = ssl.create_default_context
    certifi_path = os.path.normcase(os.path.abspath(certifi.where()))

    def create_default_context(
        purpose: ssl.Purpose = ssl.Purpose.SERVER_AUTH,
        *,
        cafile: str | None = None,
        capath: str | None = None,
        cadata: str | bytes | None = None,
    ) -> ssl.SSLContext:
        requested_path = os.path.normcase(os.path.abspath(cafile)) if cafile else None
        if requested_path == certifi_path and capath is None and cadata is None:
            return original(purpose)
        return original(
            purpose,
            cafile=cafile,
            capath=capath,
            cadata=cadata,
        )

    ssl.create_default_context = create_default_context
    try:
        yield
    finally:
        ssl.create_default_context = original


@pytest.fixture(scope="session")
def create_integration_env(tmp_path_factory: pytest.TempPathFactory) -> Callable[[Path], Path]:
    """Create isolated, pip-free integration environments through uv, offline."""
    import subprocess

    cache = tmp_path_factory.mktemp("integration-uv-cache")

    def create(environment: Path) -> Path:
        env = {**os.environ, "UV_CACHE_DIR": str(cache)}
        subprocess.run(["uv", "venv", "--offline", "--no-project", "--python", sys.executable,
                        str(environment)], env=env, check=True, capture_output=True, timeout=30)
        return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    return create


@pytest.fixture
def create_symlink():
    """Create real symlinks, skipping only Windows' missing-privilege error."""
    def create(link: Path, target: Path, *, target_is_directory: bool = False) -> None:
        try:
            link.symlink_to(target, target_is_directory=target_is_directory)
        except OSError as exc:
            if sys.platform == "win32" and getattr(exc, "winerror", None) == 1314:
                pytest.skip("Windows symlink creation requires Developer Mode or privilege")
            raise

    return create


class DisplayHistoryFixture:
    """Explicit offline setup plus snapshot reads for history projection tests."""

    def __init__(self, workspace: Path) -> None:
        from cirno_core.session.manager import SessionManager

        self.sessions = SessionManager(workspace)

    async def metadata(self, chat_id, metadata=None):
        from cirno_core.session.display_history import HISTORY_GENERATION_METADATA_KEY

        session = await self.sessions.state.get_header(f"websocket:{chat_id}")
        return {**(metadata or {}), HISTORY_GENERATION_METADATA_KEY: session.generation}

    async def message(self, **kwargs):
        from cirno_core.bus.events import OutboundMessage

        kwargs["metadata"] = await self.metadata(kwargs["chat_id"], kwargs.get("metadata"))
        return OutboundMessage(**kwargs)

    async def stream(self, channel, method, chat_id, *args, **kwargs):
        kwargs["metadata"] = await self.metadata(chat_id, kwargs.get("metadata"))
        await getattr(channel, method)(chat_id, *args, **kwargs)

    def append(self, key, record):
        from cirno_core.session.transcript import append_transcript_object

        append_transcript_object(key, record, sessions=self.sessions)

    def _project(self, name, key, *args, **kwargs):
        from cirno_core.session import transcript

        return self.sessions.project_history(key, lambda snapshot: getattr(transcript, name)(
            key, *args, history=snapshot, **kwargs,
        ))

    def read(self, key):
        return self._project("read_transcript_lines", key)

    def build(self, key, **kwargs):
        return self._project("build_webui_thread_response", key, **kwargs)

    def trace(self, key, detail_ref):
        return self._project("build_webui_trace_detail_response", key, detail_ref)

    def revision(self, key, **kwargs):
        return self._project("webui_transcript_revision", key, **kwargs)

    def prompts(self, key, **kwargs):
        from cirno_core.session.transcript import PromptPageRequest
        result = []
        while True:
            page = self.prompt_page(key, request=PromptPageRequest(offset=len(result), limit=256), **kwargs)
            result.extend(page["prompts"])
            if len(result) >= page["total"]:
                return result

    def prompt_page(self, key, **kwargs):
        return self._project("prompt_directory_page", key, **kwargs)


@pytest.fixture
async def history(tmp_path: Path):
    fixture = DisplayHistoryFixture(tmp_path)
    yield fixture
    if fixture.sessions._state is not None:
        await fixture.sessions.state.aclose()

@pytest.fixture(autouse=True)
def _isolate_agent_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Agent profiles and skills belong to an isolated Home in every test."""
    monkeypatch.setattr("cirno_core.config.home._instance_path", tmp_path / "home")
