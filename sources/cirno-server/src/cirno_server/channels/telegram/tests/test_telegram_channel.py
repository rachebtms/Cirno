from cirno_server.channels.delivery.events import send_event
from cirno_server.channels.telegram.delivery import TelegramDelivery
import asyncio
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

# Check optional Telegram dependencies before running tests
try:
    import telegram  # noqa: F401
except ImportError:
    pytest.skip("Telegram dependencies not installed (python-telegram-bot)", allow_module_level=True)

from cirno_core.bus.agent_events import ContextCompactionEvent
from cirno_core.bus.delivery import ChannelNotReadyError
from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.outbound_events import ProgressEvent, outbound_message_for_event
from cirno_core.bus.queue import MessageBus
from cirno_core.config.network import NetworkConfig
from cirno_server.channels.telegram.commands import telegram_command_text
from cirno_server.channels.telegram.config import TelegramConfig
from cirno_server.channels.telegram.formatting import (
    markdown_to_telegram_html,
    split_telegram_markdown,
)
from cirno_server.channels.telegram.limits import (
    TELEGRAM_MAX_MESSAGE_LEN,
    TELEGRAM_REPLY_CONTEXT_MAX_LEN,
    TELEGRAM_RICH_DRAFT_MIN_INTERVAL,
    TELEGRAM_RICH_MAX_LEN,
)
from cirno_server.channels.telegram.runtime import TelegramChannel
from cirno_server.channels.telegram.state import StreamBuf


@pytest.fixture
def personal_owner(_isolate_runtime_stores):
    from cirno_server.channels.telegram.binding import TelegramBinding
    binding = TelegramBinding()
    pin = binding.issue_pin()
    assert binding.verify(pin["pin"], user_id=12345, chat_id=12345, username="owner")


class _FakeHTTPXRequest:
    instances: list["_FakeHTTPXRequest"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.__class__.instances.append(self)

    @classmethod
    def clear(cls) -> None:
        cls.instances.clear()


class _FakeUpdater:
    def __init__(self, on_start_polling) -> None:
        self._on_start_polling = on_start_polling
        self.start_polling_kwargs = None
        self.start_webhook_kwargs = None

    async def start_polling(self, **kwargs) -> None:
        self.start_polling_kwargs = kwargs
        self._on_start_polling()

    async def start_webhook(self, **kwargs) -> None:
        self.start_webhook_kwargs = kwargs
        self._on_start_polling()

    async def stop(self) -> None:
        pass


class _FakeBot:
    def __init__(self) -> None:
        self.sent_messages: list[dict] = []
        self.sent_media: list[dict] = []
        self.get_me_calls = 0
        self.shutdown_calls = 0

    async def shutdown(self) -> None:
        self.shutdown_calls += 1

    async def get_me(self):
        self.get_me_calls += 1
        return SimpleNamespace(id=999, username="cirno_test")

    async def set_my_commands(self, commands) -> None:
        self.commands = commands

    async def send_message(self, **kwargs):
        self.sent_messages.append(kwargs)
        return SimpleNamespace(message_id=len(self.sent_messages))

    async def send_photo(self, **kwargs) -> None:
        self.sent_media.append({"kind": "photo", **kwargs})

    async def send_video(self, **kwargs) -> None:
        self.sent_media.append({"kind": "video", **kwargs})

    async def send_voice(self, **kwargs) -> None:
        self.sent_media.append({"kind": "voice", **kwargs})

    async def send_audio(self, **kwargs) -> None:
        self.sent_media.append({"kind": "audio", **kwargs})

    async def send_document(self, **kwargs) -> None:
        self.sent_media.append({"kind": "document", **kwargs})

    async def send_chat_action(self, **kwargs) -> None:
        pass

    async def get_file(self, file_id: str):
        """Return a fake file that 'downloads' to a path (for reply-to-media tests)."""
        async def _fake_download(path) -> None:
            pass
        return SimpleNamespace(download_to_drive=_fake_download)


class _FakeApp:
    def __init__(self, on_start_polling) -> None:
        self.bot = _FakeBot()
        self.updater = _FakeUpdater(on_start_polling)
        self.handlers = []
        self.error_handlers = []

    def add_error_handler(self, handler) -> None:
        self.error_handlers.append(handler)

    def add_handler(self, handler) -> None:
        self.handlers.append(handler)

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


class _FakeBuilder:
    def __init__(self, app: _FakeApp) -> None:
        self.app = app
        self.token_value = None
        self.request_value = None
        self.get_updates_request_value = None

    def token(self, token: str):
        self.token_value = token
        return self

    def request(self, request):
        self.request_value = request
        return self

    def get_updates_request(self, request):
        self.get_updates_request_value = request
        return self

    def proxy(self, _proxy):
        raise AssertionError("builder.proxy should not be called when request is set")

    def get_updates_proxy(self, _proxy):
        raise AssertionError("builder.get_updates_proxy should not be called when request is set")

    def build(self):
        return self.app


def _install_ready_app(channel: TelegramChannel) -> _FakeApp:
    """Install the ready app state expected by ordinary send tests."""
    app = _FakeApp(lambda: None)
    channel.connection.app = app
    channel.connection.ready.set()
    return app


def _make_telegram_update(
    *,
    chat_type: str = "private",
    text: str | None = None,
    caption: str | None = None,
    entities=None,
    caption_entities=None,
    reply_to_message=None,
    location=None,
):
    user = SimpleNamespace(id=12345, username="alice", first_name="Alice")
    message = SimpleNamespace(
        chat=SimpleNamespace(type=chat_type, is_forum=False),
        chat_id=12345 if chat_type == "private" else -100123,
        text=text,
        caption=caption,
        entities=entities or [],
        caption_entities=caption_entities or [],
        reply_to_message=reply_to_message,
        photo=None,
        voice=None,
        audio=None,
        document=None,
        location=location,
        media_group_id=None,
        message_thread_id=None,
        message_id=1,
    )
    return SimpleNamespace(message=message, effective_user=user)


def _assert_code_blocks_render_balanced(chunks: list[str]) -> None:
    for chunk in chunks:
        html = markdown_to_telegram_html(chunk)
        assert html.count("<pre><code>") == html.count("</code></pre>")


@pytest.mark.parametrize("prefix", ["Intro paragraph.\n", "Intro paragraph. "])
def test_split_telegram_markdown_inside_code_block_moves_before_fence(prefix) -> None:
    content = prefix + "```python\nprint('a')\nprint('b')\n```\nDone"

    chunks = split_telegram_markdown(content, max_len=35)

    assert chunks[0] == prefix
    assert chunks[1].startswith("```python\nprint('a')")
    _assert_code_blocks_render_balanced(chunks)


@pytest.mark.parametrize("fence", ["```", "~~~", "````"])
def test_split_telegram_markdown_long_code_block_closes_and_reopens(fence) -> None:
    content = f"{fence}python\n" + ("print('line one')\n" * 6) + f"{fence}\nDone"

    chunks = split_telegram_markdown(content, max_len=60)

    assert len(chunks) > 1
    assert all(len(chunk) <= 60 for chunk in chunks)
    assert chunks[0].startswith(f"{fence}python\n")
    assert chunks[0].endswith(f"\n{fence}")
    assert chunks[1].startswith(f"{fence}python\n")
    _assert_code_blocks_render_balanced(chunks)


def test_split_telegram_markdown_multiple_code_blocks() -> None:
    content = (
        "First\n"
        "```js\n"
        "one();\n"
        "```\n"
        "Middle paragraph here\n"
        "```py\n"
        "two()\n"
        "three()\n"
        "```\n"
        "End"
    )

    chunks = split_telegram_markdown(content, max_len=55)

    assert chunks[0].endswith("Middle paragraph here\n")
    assert chunks[1].startswith("```py\n")
    _assert_code_blocks_render_balanced(chunks)


def test_split_telegram_markdown_keeps_nested_shorter_fence() -> None:
    content = "````markdown\n```python\n" + "# raw example\n" * 40 + "```\n````"

    chunks = split_telegram_markdown(content, max_len=80)

    assert len(chunks) > 1
    assert all(len(chunk) <= 80 for chunk in chunks)
    assert all(chunk.startswith("````markdown\n") and chunk.endswith("\n````") for chunk in chunks)
    html = "".join(markdown_to_telegram_html(chunk) for chunk in chunks)
    assert html.count("# raw example") == 40
    assert html.count("```") == 2
    assert "<b>" not in html


def test_split_telegram_markdown_leading_whitespace_before_fence() -> None:
    content = "\n```python\n" + ("print('line one')\n" * 6) + "```\nDone"

    chunks = split_telegram_markdown(content, max_len=60)

    assert chunks
    assert all(chunk.strip() for chunk in chunks)
    assert chunks[0].startswith("```python\n")
    _assert_code_blocks_render_balanced(chunks)


@pytest.mark.parametrize("fence", ["```", "~~~", "````"])
def test_split_telegram_markdown_long_single_line_code_body(fence) -> None:
    """Long fence bodies with no interior newlines must still advance."""
    body = "a" * 4500
    content = f"{fence}\n{body}\n{fence}"

    chunks = split_telegram_markdown(content, TELEGRAM_MAX_MESSAGE_LEN)

    assert len(chunks) > 1
    assert all(len(chunk) <= TELEGRAM_MAX_MESSAGE_LEN for chunk in chunks)
    assert chunks[0].startswith(f"{fence}\n")
    assert chunks[0].endswith(f"\n{fence}")
    assert chunks[1].startswith(f"{fence}\n")
    reassembled = []
    for chunk in chunks:
        part = chunk.split("\n", 1)[1]
        if part.endswith(f"\n{fence}"):
            part = part[:-(len(fence) + 1)]
        elif part.endswith(fence):
            part = part[:-len(fence)]
        reassembled.append(part)
    assert "".join(reassembled) == body
    _assert_code_blocks_render_balanced(chunks)


def test_split_telegram_markdown_tiny_limit_hard_cuts_fence_prefix() -> None:
    """Adaptive HTML limits can shrink max_len to the fence+closer size."""
    body = "a" * 100
    content = f"```\n{body}"

    chunks = split_telegram_markdown(content, max_len=8)

    assert chunks
    assert all(len(chunk) <= 8 for chunk in chunks)
    assert "".join(chunks).replace("```", "").replace("\n", "") == body


def test_split_telegram_markdown_tiny_limit_with_early_body_newline() -> None:
    body = "a" * 100
    content = f"```\na\n{body}"

    chunks = split_telegram_markdown(content, max_len=8)

    assert chunks
    assert all(len(chunk) <= 8 for chunk in chunks)
    plain = "".join(chunks).replace("```", "")
    assert "a" in plain
    assert plain.count("a") >= 100


def test_split_telegram_markdown_leading_space_in_fence_body() -> None:
    body = "a" * 4500
    content = f"```\n {body}"

    chunks = split_telegram_markdown(content, TELEGRAM_MAX_MESSAGE_LEN)

    assert chunks
    assert all(len(chunk) <= TELEGRAM_MAX_MESSAGE_LEN for chunk in chunks)
    plain = "".join(chunks).replace("```", "").replace("\n", "")
    assert plain.count("a") == 4500


@pytest.mark.asyncio
async def test_start_creates_separate_pools_with_proxy(monkeypatch) -> None:
    _FakeHTTPXRequest.clear()
    config = TelegramConfig(
        enabled=True,
        token="123:abc",
        use_proxy=True,
    )
    bus = MessageBus()
    network = NetworkConfig(proxy="http://127.0.0.1:7890")
    channel = TelegramChannel(config, bus, network=network)
    app = _FakeApp(lambda: setattr(channel.connection, "running", False))
    builder = _FakeBuilder(app)

    monkeypatch.setattr("cirno_server.channels.telegram.runtime.HTTPXRequest", _FakeHTTPXRequest)
    monkeypatch.setattr(
        "cirno_server.channels.telegram.runtime.Application",
        SimpleNamespace(builder=lambda: builder),
    )

    await channel.start()

    assert len(_FakeHTTPXRequest.instances) == 2
    api_req, poll_req = _FakeHTTPXRequest.instances
    assert api_req.kwargs["proxy"] == network.proxy
    assert poll_req.kwargs["proxy"] == network.proxy
    assert api_req.kwargs["connection_pool_size"] == 32
    assert poll_req.kwargs["connection_pool_size"] == 4
    assert builder.request_value is api_req
    assert builder.get_updates_request_value.inner is poll_req
    assert callable(app.updater.start_polling_kwargs["error_callback"])
    assert any(cmd.command == "status" for cmd in app.bot.commands)
    assert any(cmd.command == "history" for cmd in app.bot.commands)
    assert any(cmd.command == "skill" for cmd in app.bot.commands)
    assert any(cmd.command == "consolidate" for cmd in app.bot.commands)
    assert any(cmd.command == "dream_log" for cmd in app.bot.commands)
    assert any(cmd.command == "dream_restore" for cmd in app.bot.commands)
    assert not any(cmd.command == "dream_prompt" for cmd in app.bot.commands)
    assert not any(cmd.command == "evaluator_prompt" for cmd in app.bot.commands)
    assert any(cmd.command == "resume" for cmd in app.bot.commands)


@pytest.mark.asyncio
async def test_start_respects_custom_pool_config(monkeypatch) -> None:
    _FakeHTTPXRequest.clear()
    config = TelegramConfig(
        enabled=True,
        token="123:abc",
        connection_pool_size=32,
        pool_timeout=10.0,
    )
    bus = MessageBus()
    channel = TelegramChannel(config, bus)
    app = _FakeApp(lambda: setattr(channel.connection, "running", False))
    builder = _FakeBuilder(app)

    monkeypatch.setattr("cirno_server.channels.telegram.runtime.HTTPXRequest", _FakeHTTPXRequest)
    monkeypatch.setattr(
        "cirno_server.channels.telegram.runtime.Application",
        SimpleNamespace(builder=lambda: builder),
    )

    await channel.start()

    api_req = _FakeHTTPXRequest.instances[0]
    poll_req = _FakeHTTPXRequest.instances[1]
    assert api_req.kwargs["connection_pool_size"] == 32
    assert api_req.kwargs["pool_timeout"] == 10.0
    assert poll_req.kwargs["pool_timeout"] == 10.0


@pytest.mark.asyncio
async def test_stalled_polling_triggers_pool_rebuild(monkeypatch) -> None:
    """When no getUpdates round trip completes for too long, the app is rebuilt."""
    _FakeHTTPXRequest.clear()
    config = TelegramConfig(enabled=True, token="123:abc")
    bus = MessageBus()
    channel = TelegramChannel(config, bus)

    apps: list[_FakeApp] = []

    def on_start_polling() -> None:
        if len(apps) >= 2:
            channel.connection.running = False

    def make_builder():
        app = _FakeApp(on_start_polling)
        apps.append(app)
        return _FakeBuilder(app)

    monkeypatch.setattr("cirno_server.channels.telegram.runtime.HTTPXRequest", _FakeHTTPXRequest)
    monkeypatch.setattr(
        "cirno_server.channels.telegram.runtime.Application",
        SimpleNamespace(builder=make_builder),
    )
    monkeypatch.setattr("cirno_server.channels.telegram.runtime.POLL_STALE_SECONDS", -1.0)
    monkeypatch.setattr("cirno_server.channels.telegram.runtime.POLL_WATCH_INTERVAL", 0.0)

    await channel.start()

    assert len(apps) == 2
    assert apps[0].updater.start_polling_kwargs is not None
    assert apps[1].updater.start_polling_kwargs is not None
    # 2 fresh pools per app
    assert len(_FakeHTTPXRequest.instances) == 4


@pytest.mark.asyncio
async def test_startup_failure_retries_with_backoff(monkeypatch) -> None:
    """Transient startup failures back off and retry until the app comes up."""
    from telegram.error import NetworkError

    _FakeHTTPXRequest.clear()
    config = TelegramConfig(enabled=True, token="123:abc")
    bus = MessageBus()
    channel = TelegramChannel(config, bus)

    apps: list[_FakeApp] = []

    def make_builder():
        app = _FakeApp(lambda: setattr(channel.connection, "running", False))
        if len(apps) < 2:
            async def _fail() -> None:
                raise NetworkError("connect failed")

            app.initialize = _fail
        apps.append(app)
        return _FakeBuilder(app)

    monkeypatch.setattr("cirno_server.channels.telegram.runtime.HTTPXRequest", _FakeHTTPXRequest)
    monkeypatch.setattr(
        "cirno_server.channels.telegram.runtime.Application",
        SimpleNamespace(builder=make_builder),
    )
    monkeypatch.setattr("cirno_server.channels.telegram.runtime.POLL_WATCH_INTERVAL", 0.0)
    monkeypatch.setattr("cirno_server.channels.telegram.runtime.RESTART_BACKOFF_INITIAL_SECONDS", 0.0)

    await channel.start()

    assert len(apps) == 3
    assert apps[0].updater.start_polling_kwargs is None
    assert apps[1].updater.start_polling_kwargs is None
    assert apps[2].updater.start_polling_kwargs is not None
    # Pools must be closed via the bot: app.shutdown() skips them here.
    assert apps[0].bot.shutdown_calls == 1
    assert apps[1].bot.shutdown_calls == 1


@pytest.mark.asyncio
async def test_terminal_startup_error_is_not_retried(monkeypatch) -> None:
    """Config errors (bad proxy, bound webhook port) must fail the channel."""
    _FakeHTTPXRequest.clear()
    config = TelegramConfig(enabled=True, token="123:abc")
    bus = MessageBus()
    channel = TelegramChannel(config, bus)

    apps: list[_FakeApp] = []

    def make_builder():
        app = _FakeApp(lambda: None)

        async def _fail() -> None:
            raise ValueError("Unknown scheme for proxy URL")

        app.initialize = _fail
        apps.append(app)
        return _FakeBuilder(app)

    monkeypatch.setattr("cirno_server.channels.telegram.runtime.HTTPXRequest", _FakeHTTPXRequest)
    monkeypatch.setattr(
        "cirno_server.channels.telegram.runtime.Application",
        SimpleNamespace(builder=make_builder),
    )
    monkeypatch.setattr("cirno_server.channels.telegram.runtime.RESTART_BACKOFF_INITIAL_SECONDS", 0.0)

    with pytest.raises(ValueError, match="proxy URL"):
        await channel.start()

    assert len(apps) == 1  # no retry loop
    assert channel.connection.app is None
    assert channel.is_running is False


@pytest.mark.asyncio
async def test_invalid_token_stops_without_retry(monkeypatch) -> None:
    """A rejected token is a config error: fail the channel instead of retrying."""
    from telegram.error import InvalidToken

    _FakeHTTPXRequest.clear()
    config = TelegramConfig(enabled=True, token="123:abc")
    bus = MessageBus()
    channel = TelegramChannel(config, bus)

    apps: list[_FakeApp] = []

    def make_builder():
        app = _FakeApp(lambda: None)

        async def _reject() -> None:
            raise InvalidToken("token rejected by Telegram")

        app.initialize = _reject
        apps.append(app)
        return _FakeBuilder(app)

    monkeypatch.setattr("cirno_server.channels.telegram.runtime.HTTPXRequest", _FakeHTTPXRequest)
    monkeypatch.setattr(
        "cirno_server.channels.telegram.runtime.Application",
        SimpleNamespace(builder=make_builder),
    )
    monkeypatch.setattr("cirno_server.channels.telegram.runtime.RESTART_BACKOFF_INITIAL_SECONDS", 0.0)

    with pytest.raises(RuntimeError) as excinfo:
        await channel.start()

    assert len(apps) == 1
    assert channel.connection.app is None
    assert channel.is_running is False
    assert "123:abc" not in str(excinfo.value)  # token must not reach the log


@pytest.mark.asyncio
async def test_stop_during_startup_does_not_leak_app(monkeypatch) -> None:
    """stop() landing while _start_app() is mid-flight must not leave the app running."""
    _FakeHTTPXRequest.clear()
    config = TelegramConfig(enabled=True, token="123:abc")
    bus = MessageBus()
    channel = TelegramChannel(config, bus)

    # Simulate stop() winning the race just before start_polling returns.
    app = _FakeApp(lambda: setattr(channel.connection, "running", False))
    builder = _FakeBuilder(app)

    monkeypatch.setattr("cirno_server.channels.telegram.runtime.HTTPXRequest", _FakeHTTPXRequest)
    monkeypatch.setattr(
        "cirno_server.channels.telegram.runtime.Application",
        SimpleNamespace(builder=lambda: builder),
    )

    await channel.start()

    assert channel.connection.app is None  # torn down, not leaked


@pytest.mark.asyncio
async def test_stop_waits_for_inflight_watchdog_teardown(monkeypatch) -> None:
    """Manager cancellation after stop() must not interrupt an active teardown."""
    _FakeHTTPXRequest.clear()
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    teardown_started = asyncio.Event()
    finish_teardown = asyncio.Event()
    app = _FakeApp(lambda: None)

    async def slow_updater_stop() -> None:
        teardown_started.set()
        await finish_teardown.wait()

    app.updater.stop = slow_updater_stop
    monkeypatch.setattr("cirno_server.channels.telegram.runtime.HTTPXRequest", _FakeHTTPXRequest)
    monkeypatch.setattr(
        "cirno_server.channels.telegram.runtime.Application",
        SimpleNamespace(builder=lambda: _FakeBuilder(app)),
    )
    monkeypatch.setattr("cirno_server.channels.telegram.runtime.POLL_STALE_SECONDS", -1.0)
    monkeypatch.setattr("cirno_server.channels.telegram.runtime.POLL_WATCH_INTERVAL", 0.0)

    start_task = asyncio.create_task(channel.start())
    await teardown_started.wait()
    assert channel.connection.app is None

    stop_task = asyncio.create_task(channel.stop())
    await asyncio.sleep(0)
    assert not stop_task.done()

    finish_teardown.set()
    await stop_task
    await start_task

    assert app.bot.shutdown_calls == 1


@pytest.mark.asyncio
async def test_send_during_rebuild_fails_instead_of_dropping(monkeypatch, telegram_owner) -> None:
    """A send that cannot reach Telegram must raise so the manager can retry."""
    monkeypatch.setattr("cirno_server.channels.telegram.connection.APP_RESTART_SEND_WAIT_SECONDS", 0.0)
    config = TelegramConfig(enabled=True, token="123:abc")
    channel = TelegramChannel(config, MessageBus())

    # Mid-rebuild: still running, but no app to send through.
    channel.connection.running = True
    channel.connection.app = None

    msg = OutboundMessage(channel="telegram", chat_id="123", content="hello")
    with pytest.raises(ChannelNotReadyError, match="restarting"):
        await channel.send(msg)
    with pytest.raises(RuntimeError, match="restarting"):
        await channel.send_delta("123", "hello", stream_id="s1")

    # A stopped channel must not report a final message as delivered.
    channel.connection.running = False
    with pytest.raises(ChannelNotReadyError, match="not running"):
        await channel.send(msg)
    with pytest.raises(ChannelNotReadyError, match="not running"):
        await channel.send_delta("123", "hello", stream_id="s1")


@pytest.mark.asyncio
async def test_send_waits_for_rebuild_to_finish(monkeypatch, telegram_owner) -> None:
    """A fast rebuild is waited out rather than surfaced as a delivery failure."""
    monkeypatch.setattr("cirno_server.channels.telegram.connection.APP_RESTART_SEND_WAIT_SECONDS", 5.0)
    config = TelegramConfig(enabled=True, token="123:abc")
    channel = TelegramChannel(config, MessageBus())

    app = _FakeApp(lambda: None)
    channel.connection.running = True
    channel.connection.app = None

    async def _finish_rebuild() -> None:
        await asyncio.sleep(0)
        channel.connection.app = app
        channel.connection.ready.set()

    rebuild = asyncio.create_task(_finish_rebuild())
    await channel.send(OutboundMessage(channel="telegram", chat_id="123", content="hello"))
    await rebuild

    assert [m["text"] for m in app.bot.sent_messages] == ["hello"]


@pytest.mark.asyncio
async def test_send_waits_for_partially_initialized_app(monkeypatch, telegram_owner) -> None:
    """A built app is not available for sends until startup marks it ready."""
    monkeypatch.setattr("cirno_server.channels.telegram.connection.APP_RESTART_SEND_WAIT_SECONDS", 5.0)
    config = TelegramConfig(enabled=True, token="123:abc")
    channel = TelegramChannel(config, MessageBus())

    app = _FakeApp(lambda: None)
    channel.connection.running = True
    channel.connection.app = app

    send_task = asyncio.create_task(
        channel.send(OutboundMessage(channel="telegram", chat_id="123", content="hello"))
    )
    await asyncio.sleep(0)
    assert not send_task.done()

    channel.connection.ready.set()
    await send_task

    assert [m["text"] for m in app.bot.sent_messages] == ["hello"]


@pytest.mark.asyncio
async def test_liveness_tracked_request_stamps_on_round_trip() -> None:
    from cirno_server.channels.telegram.liveness import _LivenessTrackedRequest

    stamps: list[int] = []

    class _Inner:
        read_timeout = 5.0

        async def initialize(self) -> None:
            pass

        async def shutdown(self) -> None:
            pass

        async def do_request(self, *args, **kwargs):
            return 200, b"{}"

    wrapped = _LivenessTrackedRequest(_Inner(), lambda: stamps.append(1))
    assert await wrapped.do_request(url="https://example.org", method="POST") == (200, b"{}")
    assert stamps == [1]


def test_webhook_config_requires_https_url_and_secret() -> None:
    with pytest.raises(ValueError, match="webhook_url is required"):
        TelegramConfig(enabled=True, token="123:abc", mode="webhook")

    with pytest.raises(ValueError, match="public HTTPS URL"):
        TelegramConfig(
            enabled=True,
            token="123:abc",
            mode="webhook",
            webhook_url="http://example.com/telegram",
            webhook_secret_token="secret",
        )

    with pytest.raises(ValueError, match="webhook_secret_token is required"):
        TelegramConfig(
            enabled=True,
            token="123:abc",
            mode="webhook",
            webhook_url="https://example.com/telegram",
        )


@pytest.mark.asyncio
async def test_start_webhook_mode(monkeypatch) -> None:
    _FakeHTTPXRequest.clear()
    config = TelegramConfig(
        enabled=True,
        token="123:abc",
        mode="webhook",
        webhook_url="https://example.com/telegram",
        webhook_listen_host="127.0.0.1",
        webhook_listen_port=8081,
        webhook_path="/telegram",
        webhook_secret_token="secret-token",
        webhook_max_connections=1,
    )
    bus = MessageBus()
    channel = TelegramChannel(config, bus)
    app = _FakeApp(lambda: setattr(channel.connection, "running", False))
    builder = _FakeBuilder(app)

    monkeypatch.setattr("cirno_server.channels.telegram.runtime.HTTPXRequest", _FakeHTTPXRequest)
    monkeypatch.setattr(
        "cirno_server.channels.telegram.runtime.Application",
        SimpleNamespace(builder=lambda: builder),
    )

    await channel.start()

    assert app.updater.start_polling_kwargs is None
    assert app.updater.start_webhook_kwargs == {
        "listen": "127.0.0.1",
        "port": 8081,
        "url_path": "telegram",
        "webhook_url": "https://example.com/telegram",
        "allowed_updates": ["message"],
        "drop_pending_updates": False,
        "secret_token": "secret-token",
        "max_connections": 1,
    }


@pytest.mark.asyncio
async def test_running_message_handler_reorders_same_session_updates(personal_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    seen: list[int] = []
    processed = asyncio.Event()

    async def fake_process(update) -> None:
        seen.append(update.message.message_id)
        if len(seen) == 2:
            processed.set()

    channel._process_message_update = fake_process
    channel.connection.running = True

    first = _make_telegram_update(text="first")
    first.update_id = 100
    first.message.message_id = 1
    second = _make_telegram_update(text="second")
    second.update_id = 101
    second.message.message_id = 2

    workers: set[asyncio.Task[None]] = set()
    try:
        await channel._on_message(second, None)
        workers.update(channel._inbound_workers.values())
        await channel._on_message(first, None)
        await asyncio.wait_for(processed.wait(), timeout=5)
        assert seen == [1, 2]
    finally:
        workers.update(channel._inbound_workers.values())
        await channel.stop()
        await asyncio.wait_for(asyncio.gather(*workers, return_exceptions=True), timeout=5)

    assert workers
    assert all(task.done() for task in workers)


@pytest.mark.asyncio
async def test_existing_message_edit_retries_timeouts(monkeypatch, telegram_owner) -> None:
    """Retrying an edit cannot create a duplicate message."""
    from telegram.error import TimedOut

    channel = TelegramChannel(TelegramConfig(token="123:abc"), MessageBus())
    _install_ready_app(channel)
    monkeypatch.setattr("cirno_server.channels.telegram.api._SEND_RETRY_BASE_DELAY", 0)
    channel.connection.app.bot.edit_message_text = AsyncMock(side_effect=[TimedOut(), TimedOut(), True])
    await channel.api.edit_formatted(123, 7, "hello", "hello")
    assert channel.connection.app.bot.edit_message_text.await_count == 3
    assert all(call.kwargs["message_id"] == 7 for call in channel.connection.app.bot.edit_message_text.await_args_list)
    assert channel.connection.app.bot.sent_messages == []


@pytest.mark.asyncio
async def test_send_text_gives_up_after_max_retries(telegram_owner) -> None:
    """_send_text raises TimedOut after exhausting all retries."""
    from telegram.error import TimedOut

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)

    async def always_timeout(**kwargs):
        raise TimedOut()

    channel.connection.app.bot.send_message = always_timeout

    import cirno_server.channels.telegram.api as tg_mod
    orig_delay = tg_mod._SEND_RETRY_BASE_DELAY
    tg_mod._SEND_RETRY_BASE_DELAY = 0.01
    try:
        with pytest.raises(TimedOut):
            await channel.api.send_text(123, "hello", None, {})
    finally:
        tg_mod._SEND_RETRY_BASE_DELAY = orig_delay

    assert channel.connection.app.bot.sent_messages == []


@pytest.mark.asyncio
async def test_send_rich_capability_error_latches_and_falls_back(telegram_owner) -> None:
    from telegram.error import BadRequest

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", rich_messages=True),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.do_api_request = AsyncMock(side_effect=BadRequest("Method not found"))

    await channel.send(OutboundMessage(channel="telegram", chat_id="123", content="**hello**"))

    assert channel.rich.disabled is True
    channel.connection.app.bot.do_api_request.assert_awaited_once()
    assert len(channel.connection.app.bot.sent_messages) == 1
    assert channel.connection.app.bot.sent_messages[0]["text"]


@pytest.mark.asyncio
async def test_send_rich_bad_request_does_not_latch_capability(telegram_owner) -> None:
    from telegram.error import BadRequest

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", rich_messages=True),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.do_api_request = AsyncMock(
        side_effect=BadRequest("Bad Request: message to reply not found")
    )

    await channel.send(OutboundMessage(channel="telegram", chat_id="123", content="**hello**"))

    assert channel.rich.disabled is False
    channel.connection.app.bot.do_api_request.assert_awaited_once()
    assert len(channel.connection.app.bot.sent_messages) == 1


@pytest.mark.asyncio
async def test_rich_messages_default_skips_send_rich_message(telegram_owner) -> None:
    """By default, sendRichMessage should not be called."""
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.do_api_request = AsyncMock()

    await channel.send(OutboundMessage(channel="telegram", chat_id="123", content="**hello**"))

    channel.connection.app.bot.do_api_request.assert_not_called()
    assert len(channel.connection.app.bot.sent_messages) == 1
    assert channel.connection.app.bot.sent_messages[0]["text"]


@pytest.mark.asyncio
async def test_send_delta_rich_stream_updates_one_draft_then_persists_final(telegram_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(
            enabled=True,
            token="123:abc",
            rich_messages=True,
            stream_edit_interval=0.1,
        ),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.do_api_request = AsyncMock(return_value=True)

    await channel.send_delta(
        "123",
        "# head",
        {"is_group": False, "message_thread_id": 42},
        stream_id="s:0",
    )
    draft_id = channel.streams.buffers["123"].draft_id
    assert draft_id is not None and draft_id != 0
    channel.streams.buffers["123"].last_edit = 0.0
    metadata = {"is_group": False, "message_thread_id": 42}
    await channel.send_delta("123", "\n\n**body**", metadata, stream_id="s:0")
    await channel.send_delta("123", "", metadata, stream_id="s:0", stream_end=True)

    calls = channel.connection.app.bot.do_api_request.call_args_list
    assert [call.args[0] for call in calls] == [
        "sendRichMessageDraft",
        "sendRichMessageDraft",
        "sendRichMessage",
    ]
    assert calls[0].kwargs["api_kwargs"] == {
        "chat_id": 123,
        "draft_id": draft_id,
        "message_thread_id": 42,
        "rich_message": {"markdown": "# head"},
    }
    assert calls[1].kwargs["api_kwargs"]["draft_id"] == draft_id
    assert calls[1].kwargs["api_kwargs"]["rich_message"] == {
        "markdown": "# head\n\n**body**",
    }
    assert "draft_id" not in calls[2].kwargs["api_kwargs"]
    assert calls[2].kwargs["api_kwargs"]["message_thread_id"] == 42
    assert calls[2].kwargs["api_kwargs"]["rich_message"] == {
        "markdown": "# head\n\n**body**",
    }
    assert channel.connection.app.bot.sent_messages == []
    assert "123" not in channel.streams.buffers


@pytest.mark.asyncio
async def test_send_delta_rich_initial_rejection_falls_back_to_legacy_preview(telegram_owner) -> None:
    from telegram.error import BadRequest

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", rich_messages=True),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.do_api_request = AsyncMock(side_effect=BadRequest("can't parse rich message"))

    await channel.send_delta(
        "123", "# head", {"is_group": False}, stream_id="s:0",
    )

    channel.connection.app.bot.do_api_request.assert_awaited_once()
    assert channel.connection.app.bot.do_api_request.call_args.args[0] == "sendRichMessageDraft"
    assert channel.rich.disabled is False
    assert channel.connection.app.bot.sent_messages[0]["text"] == "head"
    assert channel.streams.buffers["123"].message_id == 1
    assert channel.streams.buffers["123"].draft_id is None


@pytest.mark.asyncio
async def test_send_delta_rich_draft_rejection_falls_back_to_legacy_preview(telegram_owner) -> None:
    from telegram.error import BadRequest

    channel = TelegramChannel(
        TelegramConfig(
            enabled=True,
            token="123:abc",
            rich_messages=True,
            stream_edit_interval=0.1,
        ),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.streams.buffers["123"] = StreamBuf(
        text="# head", draft_id=17, last_edit=0.0, stream_id="s:0",
    )
    channel.connection.app.bot.do_api_request = AsyncMock(side_effect=BadRequest("can't parse rich message"))

    await channel.send_delta("123", "\nbody", stream_id="s:0")

    assert channel.connection.app.bot.do_api_request.call_args.args[0] == "sendRichMessageDraft"
    rich_kwargs = channel.connection.app.bot.do_api_request.call_args.kwargs["api_kwargs"]
    assert rich_kwargs["draft_id"] == 17
    assert rich_kwargs["rich_message"] == {"markdown": "# head\nbody"}
    assert channel.connection.app.bot.sent_messages[0]["text"] == "head\nbody"
    assert channel.streams.buffers["123"].message_id == 1
    assert channel.streams.buffers["123"].draft_id is None


@pytest.mark.asyncio
async def test_send_delta_rich_stream_end_persists_draft_with_send_rich_message(telegram_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", rich_messages=True),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.streams.buffers["123"] = StreamBuf(
        text="# heading\n\n| a | b |\n|---|---|\n| 1 | 2 |",
        draft_id=17,
        last_edit=0.0,
        stream_id="s:0",
    )
    channel.connection.app.bot.do_api_request = AsyncMock(return_value=True)
    channel.connection.app.bot.delete_message = AsyncMock()

    await channel.send_delta("123", "", stream_id="s:0", stream_end=True)

    call = channel.connection.app.bot.do_api_request.call_args
    assert call.args[0] == "sendRichMessage"
    assert "draft_id" not in call.kwargs["api_kwargs"]
    assert call.kwargs["api_kwargs"]["rich_message"]["markdown"].startswith("# heading")
    channel.connection.app.bot.delete_message.assert_not_awaited()
    assert channel.connection.app.bot.sent_messages == []
    assert "123" not in channel.streams.buffers


@pytest.mark.asyncio
async def test_send_delta_rich_stream_end_timeout_is_not_retried(telegram_owner) -> None:
    from telegram.error import TimedOut

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", rich_messages=True),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.streams.buffers["123"] = StreamBuf(
        text="final answer",
        draft_id=17,
        last_edit=0.0,
        stream_id="s:0",
    )
    channel.connection.app.bot.do_api_request = AsyncMock(side_effect=TimedOut("ambiguous timeout"))

    with pytest.raises(TimedOut, match="ambiguous timeout"):
        await channel.send_delta("123", "", stream_id="s:0", stream_end=True)

    channel.connection.app.bot.do_api_request.assert_awaited_once()
    assert channel.connection.app.bot.do_api_request.call_args.args[0] == "sendRichMessage"
    assert channel.connection.app.bot.sent_messages == []
    assert channel.streams.buffers["123"].delivery_error is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("rich_error", [None, "can't parse rich message", "method not found"])
async def test_rich_stream_final_retry_keeps_only_unsent_chunks(
    rich_error: str | None,
    telegram_owner,
    monkeypatch,
) -> None:
    from telegram.error import BadRequest, RetryAfter

    monkeypatch.setattr("cirno_server.channels.telegram.api._SEND_MAX_RETRIES", 1)
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", rich_messages=True),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.edit_message_text = AsyncMock()
    delivered: list[str] = []
    failed = False

    async def deliver(text):
        nonlocal failed
        if text.startswith("B") and not failed:
            failed = True
            raise RetryAfter(0)
        delivered.append(text)
        return SimpleNamespace(message_id=len(delivered))

    async def api(method, *, api_kwargs):
        if method == "sendRichMessage":
            if rich_error:
                raise BadRequest(rich_error)
            return await deliver(api_kwargs["rich_message"]["markdown"])
        return True

    async def send_message(**kwargs):
        return await deliver(kwargs["text"])

    channel.connection.app.bot.do_api_request = AsyncMock(side_effect=api)
    channel.connection.app.bot.send_message = AsyncMock(side_effect=send_message)
    metadata = {"is_group": False}
    await channel.send_delta("123", "A", metadata, stream_id="s:0")
    delta = "A" * (TELEGRAM_RICH_MAX_LEN - 1) + "\n" + "B" * TELEGRAM_RICH_MAX_LEN + "\nC"
    await channel.send_delta("123", delta, metadata, stream_id="s:0")

    with pytest.raises(RetryAfter):
        await channel.send_delta(
            "123", "", metadata, stream_id="s:0", stream_end=True,
        )
    assert "".join(delivered) == "A" * TELEGRAM_RICH_MAX_LEN
    assert channel.streams.buffers["123"].text.replace("\n", "") == (
        (delivered[-1] if channel.streams.buffers["123"].message_id is not None else "")
        + "B" * TELEGRAM_RICH_MAX_LEN + "C"
    )

    await channel.send_delta(
        "123", "", metadata, stream_id="s:0", stream_end=True,
    )

    assert "".join(delivered).replace("\n", "") == (
        "A" * TELEGRAM_RICH_MAX_LEN + "B" * TELEGRAM_RICH_MAX_LEN + "C"
    )
    assert "123" not in channel.streams.buffers


@pytest.mark.asyncio
async def test_rich_stream_overflow_failure_does_not_drop_same_text_next_delta(
    monkeypatch: pytest.MonkeyPatch,
    telegram_owner,
) -> None:
    from telegram.error import RetryAfter

    monkeypatch.setattr("cirno_server.channels.telegram.limits.TELEGRAM_RICH_MAX_LEN", 4)
    monkeypatch.setattr("cirno_server.channels.telegram.api._SEND_MAX_RETRIES", 1)
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", rich_messages=True),
        MessageBus(),
    )
    _install_ready_app(channel)
    delivered: list[str] = []
    failed = False

    async def api(method, *, api_kwargs):
        nonlocal failed
        if method == "sendRichMessage":
            text = api_kwargs["rich_message"]["markdown"]
            if text == "BBBB" and not failed:
                failed = True
                raise RetryAfter(0)
            delivered.append(text)
        return True

    channel.connection.app.bot.do_api_request = AsyncMock(side_effect=api)
    metadata = {"is_group": False}
    await channel.send_delta("123", "A", metadata, stream_id="s:0")
    channel.streams.buffers["123"].last_edit = 0.0
    repeated_delta = "AAA\nBBBB\nC"

    with pytest.raises(RetryAfter):
        await channel.send_delta("123", repeated_delta, metadata, stream_id="s:0")

    assert delivered == ["AAAA"]
    assert channel.streams.buffers["123"].text == "BBBB\nC"

    await channel.send_delta("123", repeated_delta, metadata, stream_id="s:0")
    await channel.send_delta("123", "", metadata, stream_id="s:0", stream_end=True)

    assert "".join(delivered).replace("\n", "") == (
        "A" + repeated_delta + repeated_delta
    ).replace("\n", "")
    assert "123" not in channel.streams.buffers


@pytest.mark.asyncio
async def test_send_delta_rich_does_not_flush_at_legacy_limit(telegram_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(
            enabled=True,
            token="123:abc",
            rich_messages=True,
            stream_edit_interval=0.1,
        ),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.streams.buffers["123"] = StreamBuf(
        text="x" * TELEGRAM_MAX_MESSAGE_LEN,
        draft_id=17,
        last_edit=0.0,
        stream_id="s:0",
    )
    channel.connection.app.bot.do_api_request = AsyncMock(return_value=True)

    await channel.send_delta("123", "y", stream_id="s:0")

    channel.connection.app.bot.do_api_request.assert_awaited_once()
    call = channel.connection.app.bot.do_api_request.call_args
    assert call.args[0] == "sendRichMessageDraft"
    assert call.kwargs["api_kwargs"]["draft_id"] == 17
    assert len(call.kwargs["api_kwargs"]["rich_message"]["markdown"]) == (
        TELEGRAM_MAX_MESSAGE_LEN + 1
    )
    assert channel.connection.app.bot.sent_messages == []
    assert channel.streams.buffers["123"].text.endswith("y")


@pytest.mark.asyncio
async def test_flush_stream_overflow_uses_rich_limit_and_reanchors_tail(telegram_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", rich_messages=True),
        MessageBus(),
    )
    _install_ready_app(channel)
    text = "x" * TELEGRAM_RICH_MAX_LEN + "\n" + "**tail**"
    channel.streams.buffers["123"] = StreamBuf(
        text=text,
        draft_id=17,
        last_edit=0.0,
        stream_id="s:0",
    )
    channel.connection.app.bot.do_api_request = AsyncMock(return_value=True)

    await channel.overflow.flush_stream_overflow(
        123, channel.streams.buffers["123"], {"message_thread_id": 42},
    )

    calls = channel.connection.app.bot.do_api_request.call_args_list
    assert [call.args[0] for call in calls] == [
        "sendRichMessage",
        "sendRichMessageDraft",
    ]
    first = calls[0].kwargs["api_kwargs"]["rich_message"]["markdown"]
    tail = calls[1].kwargs["api_kwargs"]["rich_message"]["markdown"]
    assert len(first) <= TELEGRAM_RICH_MAX_LEN
    assert len(tail) <= TELEGRAM_RICH_MAX_LEN
    assert calls[1].kwargs["api_kwargs"]["message_thread_id"] == 42
    assert channel.streams.buffers["123"].message_id is None
    assert channel.streams.buffers["123"].draft_id not in (None, 0, 17)
    assert channel.streams.buffers["123"].text == tail
    assert channel.connection.app.bot.sent_messages == []


@pytest.mark.asyncio
async def test_flush_stream_overflow_rich_limit_counts_unicode_characters(telegram_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", rich_messages=True),
        MessageBus(),
    )
    _install_ready_app(channel)
    text = "测" * TELEGRAM_RICH_MAX_LEN + "\n尾"
    buf = StreamBuf(text=text, draft_id=17, last_edit=0.0, stream_id="s:0")
    channel.connection.app.bot.do_api_request = AsyncMock(return_value=True)

    await channel.overflow.flush_stream_overflow(123, buf, {})

    calls = channel.connection.app.bot.do_api_request.call_args_list
    first = calls[0].kwargs["api_kwargs"]["rich_message"]["markdown"]
    assert len(first) == TELEGRAM_RICH_MAX_LEN
    assert len(first.encode("utf-8")) > TELEGRAM_RICH_MAX_LEN
    assert buf.text == "尾"


@pytest.mark.asyncio
async def test_send_delta_rich_draft_rate_is_limited_to_40_per_30_seconds(telegram_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(
            enabled=True,
            token="123:abc",
            rich_messages=True,
            stream_edit_interval=0.1,
        ),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.do_api_request = AsyncMock(return_value=True)

    await channel.send_delta(
        "123", "first", {"is_group": False}, stream_id="s:0",
    )
    first_edit = channel.streams.buffers["123"].last_edit
    await channel.send_delta("123", " second", stream_id="s:0")

    assert TELEGRAM_RICH_DRAFT_MIN_INTERVAL == 30 / 40
    channel.connection.app.bot.do_api_request.assert_awaited_once()
    assert channel.streams.buffers["123"].last_edit == first_edit


@pytest.mark.asyncio
async def test_send_delta_rejects_group_delivery_before_creating_a_preview(telegram_owner) -> None:
    from cirno_core.bus.delivery import DeliveryRejectedError

    channel = TelegramChannel(TelegramConfig(token="123:abc", rich_messages=True), MessageBus())
    _install_ready_app(channel)
    channel.connection.app.bot.do_api_request = AsyncMock()
    with pytest.raises(DeliveryRejectedError, match="private"):
        await channel.send_delta("-100123", "**hello**", {"is_group": True}, stream_id="s:0")
    channel.connection.app.bot.do_api_request.assert_not_awaited()
    assert channel.connection.app.bot.sent_messages == []
    assert channel.streams.buffers == {}


@pytest.mark.asyncio
async def test_on_error_logs_network_issues_as_warning(monkeypatch) -> None:
    from telegram.error import NetworkError

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    recorded: list[tuple[str, str]] = []

    monkeypatch.setattr(
        channel.logger,
        "warning",
        lambda message, error: recorded.append(("warning", message.format(error))),
    )
    monkeypatch.setattr(
        channel.logger,
        "error",
        lambda message, error: recorded.append(("error", message.format(error))),
    )

    await channel._on_error(object(), SimpleNamespace(error=NetworkError("proxy disconnected")))

    assert recorded == [("warning", "network issue: proxy disconnected")]


@pytest.mark.asyncio
async def test_on_error_summarizes_empty_network_error(monkeypatch) -> None:
    from telegram.error import NetworkError

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    recorded: list[tuple[str, str]] = []

    monkeypatch.setattr(
        channel.logger,
        "warning",
        lambda message, error: recorded.append(("warning", message.format(error))),
    )

    await channel._on_error(object(), SimpleNamespace(error=NetworkError("")))

    assert recorded == [("warning", "network issue: NetworkError")]


@pytest.mark.asyncio
async def test_on_error_keeps_non_network_exceptions_as_error(monkeypatch) -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    recorded: list[tuple[str, str]] = []

    monkeypatch.setattr(
        channel.logger,
        "warning",
        lambda message, error: recorded.append(("warning", message.format(error))),
    )
    monkeypatch.setattr(
        channel.logger,
        "error",
        lambda message, error: recorded.append(("error", message.format(error))),
    )

    await channel._on_error(object(), SimpleNamespace(error=RuntimeError("boom")))

    assert recorded == [("error", "error: boom")]


@pytest.mark.asyncio
async def test_send_delta_stream_end_raises_and_keeps_buffer_on_failure(telegram_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.edit_message_text = AsyncMock(side_effect=RuntimeError("boom"))
    channel.streams.buffers["123"] = StreamBuf(text="hello", message_id=7, last_edit=0.0)

    with pytest.raises(RuntimeError, match="boom"):
        await channel.send_delta("123", "", stream_end=True)

    assert "123" in channel.streams.buffers


@pytest.mark.asyncio
async def test_send_delta_merge_next_preserves_buffer(telegram_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.edit_message_text = AsyncMock()
    channel.streams.buffers["123"] = StreamBuf(
        text="first-",
        message_id=7,
        last_edit=float("inf"),
        stream_id="s:0",
    )

    await channel.send_delta(
        "123",
        "boundary",
        stream_id="s:0",
        stream_end=True,
        merge_next=True,
    )

    assert channel.streams.buffers["123"].text == "first-boundary"
    channel.connection.app.bot.edit_message_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_delta_stream_end_treats_not_modified_as_success(telegram_owner) -> None:
    from telegram.error import BadRequest

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.edit_message_text = AsyncMock(side_effect=BadRequest("Message is not modified"))
    channel.streams.buffers["123"] = StreamBuf(text="hello", message_id=7, last_edit=0.0, stream_id="s:0")

    await channel.send_delta("123", "", stream_id="s:0", stream_end=True)

    assert "123" not in channel.streams.buffers


@pytest.mark.asyncio
async def test_send_delta_stream_end_does_not_fallback_on_network_timeout(
    monkeypatch: pytest.MonkeyPatch,
    telegram_owner,
) -> None:
    """TimedOut during HTML edit should propagate, never fall back to plain text."""
    from telegram.error import TimedOut

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    monkeypatch.setattr("cirno_server.channels.telegram.api._SEND_RETRY_BASE_DELAY", 0)
    # _call_with_retry retries TimedOut up to 3 times, so the mock will be called
    # multiple times – but all calls must be with parse_mode="HTML" (no plain fallback).
    channel.connection.app.bot.edit_message_text = AsyncMock(side_effect=TimedOut("network timeout"))
    channel.streams.buffers["123"] = StreamBuf(text="hello", message_id=7, last_edit=0.0)

    with pytest.raises(TimedOut, match="network timeout"):
        await channel.send_delta("123", "", stream_end=True)

    # Every call to edit_message_text must have used parse_mode="HTML" —
    # no plain-text fallback call should have been made.
    for call in channel.connection.app.bot.edit_message_text.call_args_list:
        assert call.kwargs.get("parse_mode") == "HTML"
    assert channel.connection.app.bot.edit_message_text.await_count == 3
    # Buffer should still be present (not cleaned up on error)
    assert "123" in channel.streams.buffers


@pytest.mark.asyncio
async def test_send_delta_stream_end_does_not_fallback_on_network_error(telegram_owner) -> None:
    """NetworkError during HTML edit should propagate, never fall back to plain text."""
    from telegram.error import NetworkError

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.edit_message_text = AsyncMock(side_effect=NetworkError("connection reset"))
    channel.streams.buffers["123"] = StreamBuf(text="hello", message_id=7, last_edit=0.0)

    with pytest.raises(NetworkError, match="connection reset"):
        await channel.send_delta("123", "", stream_end=True)

    # Every call to edit_message_text must have used parse_mode="HTML" —
    # no plain-text fallback call should have been made.
    for call in channel.connection.app.bot.edit_message_text.call_args_list:
        assert call.kwargs.get("parse_mode") == "HTML"
    # Buffer should still be present (not cleaned up on error)
    assert "123" in channel.streams.buffers


@pytest.mark.asyncio
async def test_send_delta_stream_end_falls_back_on_bad_request(telegram_owner) -> None:
    """BadRequest (HTML parse error) should still trigger plain-text fallback."""
    from telegram.error import BadRequest

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)

    # First call (HTML) raises BadRequest, second call (plain) succeeds
    channel.connection.app.bot.edit_message_text = AsyncMock(
        side_effect=[BadRequest("Can't parse entities"), None]
    )
    channel.streams.buffers["123"] = StreamBuf(text="hello <bad>", message_id=7, last_edit=0.0)

    await channel.send_delta("123", "", stream_end=True)

    # edit_message_text should have been called twice: once for HTML, once for plain fallback
    assert channel.connection.app.bot.edit_message_text.call_count == 2
    # Second call should not use parse_mode="HTML"
    second_call_kwargs = channel.connection.app.bot.edit_message_text.call_args_list[1].kwargs
    assert "parse_mode" not in second_call_kwargs or second_call_kwargs.get("parse_mode") is None
    # Buffer should be cleaned up on success
    assert "123" not in channel.streams.buffers


@pytest.mark.asyncio
async def test_send_delta_stream_end_splits_oversized_reply(telegram_owner) -> None:
    """Final streamed reply exceeding Telegram limit is split into chunks.

    The fix converts markdown to HTML first, then splits by 4096 (actual Telegram
    limit), ensuring the edited message always fits within Telegram's constraint.
    Previously, the code split by 4000 (TELEGRAM_MAX_MESSAGE_LEN) before HTML
    conversion, which could still overflow when HTML tags were added.
    """
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.edit_message_text = AsyncMock()
    channel.connection.app.bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=99))

    oversized = "x" * (4000 + 500)
    channel.streams.buffers["123"] = StreamBuf(text=oversized, message_id=7, last_edit=0.0)

    await channel.send_delta("123", "", stream_end=True)

    channel.connection.app.bot.edit_message_text.assert_called_once()
    edit_text = channel.connection.app.bot.edit_message_text.call_args.kwargs.get("text", "")
    assert len(edit_text) <= 4096, f"edit_text length {len(edit_text)} exceeds Telegram's 4096 limit"

    channel.connection.app.bot.send_message.assert_called_once()
    send_text = channel.connection.app.bot.send_message.call_args.kwargs.get("text", "")
    assert len(send_text) <= 4096
    assert "123" not in channel.streams.buffers


@pytest.mark.asyncio
async def test_send_delta_stream_end_html_expansion_does_not_overflow(telegram_owner) -> None:
    """Markdown that expands when converted to HTML is still split correctly.

    This is the actual bug from issue #3315: markdown like **bold** expands to
    <b>bold</b>, adding ~33% characters. A 3600-char message with heavy markdown
    could become 4800+ chars after HTML conversion, exceeding 4096 limit.
    The fix converts to HTML first, THEN splits by 4096.
    """
    from cirno_server.channels.telegram.formatting import markdown_to_telegram_html

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.edit_message_text = AsyncMock()
    channel.connection.app.bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=99))

    markdown_text = "**bold** " * 400  # 3600 chars raw, expands ~33% to 4800 HTML
    raw_len = len(markdown_text)
    html_len = len(markdown_to_telegram_html(markdown_text))
    assert html_len > 4096, f"Test precondition failed: HTML should exceed 4096 (was {html_len})"

    channel.streams.buffers["123"] = StreamBuf(text=markdown_text, message_id=7, last_edit=0.0)

    await channel.send_delta("123", "", stream_end=True)

    channel.connection.app.bot.edit_message_text.assert_called_once()
    edit_text = channel.connection.app.bot.edit_message_text.call_args.kwargs.get("text", "")
    assert len(edit_text) <= 4096, (
        f"HTML text length {len(edit_text)} exceeds Telegram's 4096 limit. "
        f"Raw was {raw_len}, HTML was {html_len}."
    )

    channel.connection.app.bot.send_message.assert_called_once()
    assert "123" not in channel.streams.buffers


@pytest.mark.asyncio
@pytest.mark.parametrize("fence", ["```", "~~~", "````"])
async def test_send_delta_stream_end_splits_long_code_block_before_html_rendering(fence, telegram_owner) -> None:
    """Final streamed replies must not split Telegram HTML inside <pre><code>."""
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.edit_message_text = AsyncMock()
    channel.connection.app.bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=99))

    raw_text = f"{fence}python\n" + ("print(\"line\")\n" * 450) + f"{fence}\nDone"
    channel.streams.buffers["123"] = StreamBuf(text=raw_text, message_id=7, last_edit=0.0)

    await channel.send_delta("123", "", stream_end=True)

    html_chunks = [
        channel.connection.app.bot.edit_message_text.call_args.kwargs.get("text", ""),
        *[
            call.kwargs.get("text", "")
            for call in channel.connection.app.bot.send_message.call_args_list
        ],
    ]
    assert len(html_chunks) > 1
    for html in html_chunks:
        assert len(html) <= 4096
        assert html.count("<pre><code>") == html.count("</code></pre>")
        if 'print("line")' in html:
            assert html.startswith("<pre><code>")
    assert "".join(html_chunks).count('print("line")') == 450
    assert "123" not in channel.streams.buffers


@pytest.mark.asyncio
async def test_send_delta_new_stream_id_replaces_stale_buffer(telegram_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.streams.buffers["123"] = StreamBuf(
        text="hello",
        message_id=7,
        last_edit=0.0,
        stream_id="old:0",
    )

    await channel.send_delta("123", "world", stream_id="new:0")

    buf = channel.streams.buffers["123"]
    assert buf.text == "world"
    assert buf.stream_id == "new:0"
    assert buf.message_id == 1


@pytest.mark.asyncio
async def test_send_delta_incremental_edit_treats_not_modified_as_success(telegram_owner) -> None:
    from telegram.error import BadRequest

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.streams.buffers["123"] = StreamBuf(text="hello", message_id=7, last_edit=0.0, stream_id="s:0")
    channel.connection.app.bot.edit_message_text = AsyncMock(side_effect=BadRequest("Message is not modified"))

    await channel.send_delta("123", "", stream_id="s:0")

    assert channel.streams.buffers["123"].last_edit > 0.0


@pytest.mark.asyncio
async def test_send_delta_incremental_edit_splits_oversized_buffer(telegram_owner) -> None:
    """Mid-stream overflow: once buf.text exceeds Telegram's limit, split into
    chunks, edit the current message with the first chunk, and re-anchor the
    buffer to a new message for the tail so further deltas keep streaming."""
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.edit_message_text = AsyncMock()
    channel.connection.app.bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=99))

    first_chunk = f"**{'x' * 3900}**\n"
    tail = "**tail** " * 50
    oversized = first_chunk + tail
    channel.streams.buffers["123"] = StreamBuf(
        text=oversized, message_id=7, last_edit=0.0, stream_id="s:0"
    )

    await channel.send_delta("123", "y", stream_id="s:0")

    channel.connection.app.bot.edit_message_text.assert_called_once()
    edit_kwargs = channel.connection.app.bot.edit_message_text.call_args.kwargs
    assert edit_kwargs["text"] == markdown_to_telegram_html(first_chunk.rstrip())
    assert edit_kwargs["parse_mode"] == "HTML"

    channel.connection.app.bot.send_message.assert_called_once()
    send_kwargs = channel.connection.app.bot.send_message.call_args.kwargs
    assert send_kwargs["parse_mode"] == "HTML"
    buf = channel.streams.buffers["123"]
    assert buf.message_id == 99
    assert buf.text == tail + "y"
    assert send_kwargs["text"] == markdown_to_telegram_html(buf.text)
    assert buf.last_edit > 0.0


@pytest.mark.asyncio
async def test_send_delta_incremental_html_expansion_does_not_overflow(telegram_owner) -> None:
    """Mid-stream HTML chunks stay within Telegram's rendered payload limit."""
    from cirno_server.channels.telegram.limits import TELEGRAM_HTML_MAX_LEN

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.edit_message_text = AsyncMock()
    channel.connection.app.bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=99))

    oversized = "**bold** " * 501
    assert len(markdown_to_telegram_html(oversized)) > TELEGRAM_HTML_MAX_LEN
    channel.streams.buffers["123"] = StreamBuf(
        text=oversized, message_id=7, last_edit=0.0, stream_id="s:0"
    )

    await channel.send_delta("123", "y", stream_id="s:0")

    payloads = [
        channel.connection.app.bot.edit_message_text.call_args.kwargs,
        *[call.kwargs for call in channel.connection.app.bot.send_message.call_args_list],
    ]
    assert len(payloads) > 1
    assert all(payload["parse_mode"] == "HTML" for payload in payloads)
    assert all(len(payload["text"]) <= TELEGRAM_HTML_MAX_LEN for payload in payloads)

    buf = channel.streams.buffers["123"]
    assert payloads[-1]["text"] == markdown_to_telegram_html(buf.text)
    assert "<b>" not in buf.text


@pytest.mark.asyncio
async def test_send_delta_incremental_html_parse_failure_falls_back_to_plain(telegram_owner) -> None:
    """Telegram HTML rejections retry overflow chunks as plain text."""
    from telegram.error import BadRequest

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.edit_message_text = AsyncMock(
        side_effect=[BadRequest("Can't parse entities"), None]
    )
    channel.connection.app.bot.send_message = AsyncMock(
        side_effect=[BadRequest("Can't parse entities"), SimpleNamespace(message_id=99)]
    )

    first_chunk = f"**{'x' * 3900}**\n"
    tail = "**tail** " * 50
    channel.streams.buffers["123"] = StreamBuf(
        text=first_chunk + tail, message_id=7, last_edit=0.0, stream_id="s:0"
    )

    await channel.send_delta("123", "y", stream_id="s:0")

    edit_calls = channel.connection.app.bot.edit_message_text.call_args_list
    assert edit_calls[0].kwargs["parse_mode"] == "HTML"
    assert edit_calls[1].kwargs["text"] == first_chunk.rstrip()
    assert "parse_mode" not in edit_calls[1].kwargs

    send_calls = channel.connection.app.bot.send_message.call_args_list
    assert send_calls[0].kwargs["parse_mode"] == "HTML"
    assert send_calls[1].kwargs["text"] == tail + "y"
    assert "parse_mode" not in send_calls[1].kwargs
    assert channel.streams.buffers["123"].text == tail + "y"


@pytest.mark.asyncio
async def test_send_delta_initial_send_keeps_message_in_thread(telegram_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)

    await channel.send_delta(
        "123",
        "hello",
        {"message_thread_id": 42},
        stream_id="s:0",
    )

    assert channel.connection.app.bot.sent_messages[0]["message_thread_id"] == 42


def test_get_extension_falls_back_to_original_filename() -> None:
    channel = TelegramChannel(TelegramConfig(), MessageBus())

    assert channel._get_extension("file", None, "report.pdf") == ".pdf"
    assert channel._get_extension("file", None, "archive.tar.gz") == ".tar.gz"


def test_telegram_has_no_group_policy_setting() -> None:
    assert "group_policy" not in TelegramConfig.model_fields


@pytest.mark.asyncio
async def test_send_progress_keeps_message_in_topic(telegram_owner) -> None:
    config = TelegramConfig(enabled=True, token="123:abc")
    channel = TelegramChannel(config, MessageBus())
    _install_ready_app(channel)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="123",
            content="hello",
            event=ProgressEvent(content="hello"),
            metadata={"message_thread_id": 42},
        )
    )

    assert channel.connection.app.bot.sent_messages[0]["message_thread_id"] == 42


@pytest.mark.asyncio
async def test_structured_tool_start_sends_quote_in_topic(telegram_owner) -> None:
    config = TelegramConfig(
        enabled=True, token="123:abc", reply_to_message=True,
    )
    channel = TelegramChannel(config, MessageBus())
    app = _install_ready_app(channel)
    channel.tool_status_summary_max_chars = 20
    msg = outbound_message_for_event(
        channel="telegram",
        chat_id="123",
        event=ProgressEvent(tool_hint=True, tool_events=[{
            "phase": "start", "call_id": "call-1", "name": "web_search",
            "arguments": {"query": "abcdefghijklmnopqrstuvwxyz"},
        }]),
        metadata={"message_id": 10, "message_thread_id": 42},
    )

    await send_event(channel, channel.prepare_tool_events(msg))

    assert len(app.bot.sent_messages) == 1
    sent = app.bot.sent_messages[0]
    assert sent["chat_id"] == 123
    assert sent["text"] == '<blockquote expandable>search "abcdefghijklmnopqrs…"</blockquote>'
    assert sent["parse_mode"] == "HTML"
    assert sent["message_thread_id"] == 42
    assert sent["reply_parameters"].message_id == 10
    assert msg.content == ""
    assert msg.event.content == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("media_url", [
    "https://example.com/cat.jpg",
    "https://example.com/cat.jpg?width=672",
    "https://example.com/cat.jpg#preview",
])
async def test_send_remote_media_url_after_security_validation(monkeypatch, media_url, telegram_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    monkeypatch.setattr("cirno_server.channels.telegram.delivery.validate_url_target", lambda url: (True, ""))

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="123",
            content="",
            media=[media_url],
        )
    )

    assert channel.connection.app.bot.sent_media == [
        {
            "kind": "photo",
            "chat_id": 123,
            "photo": media_url,
            "reply_parameters": None,
        }
    ]


@pytest.mark.asyncio
async def test_send_local_media_preserves_filename(tmp_path: Path, telegram_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    attachment = tmp_path / "report.final.md"
    attachment.write_bytes(b"# Report\n")

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="123",
            content="",
            media=[str(attachment)],
        )
    )

    assert channel.connection.app.bot.sent_media == [
        {
            "kind": "document",
            "chat_id": 123,
            "document": b"# Report\n",
            "reply_parameters": None,
            "filename": "report.final.md",
        }
    ]


@pytest.mark.asyncio
async def test_send_blocks_unsafe_remote_media_url(monkeypatch, telegram_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    monkeypatch.setattr(
        "cirno_server.channels.telegram.delivery.validate_url_target",
        lambda url: (False, "Blocked: example.com resolves to private/internal address 127.0.0.1"),
    )

    with pytest.raises(ValueError, match="unsafe media URL"):
        await channel.send(
            OutboundMessage(
                channel="telegram",
                chat_id="123",
                content="",
                media=["http://example.com/internal.jpg"],
            )
        )

    assert channel.connection.app.bot.sent_media == []
    assert channel.connection.app.bot.sent_messages == [
        {
            "chat_id": 123,
            "text": "[File delivery could not be confirmed: internal.jpg]",
            "reply_parameters": None,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("chat_type", ["group", "supergroup", "channel"])
@pytest.mark.parametrize("handler", ["_on_message", "_forward_command", "_on_start", "_on_help"])
async def test_non_private_updates_are_rejected_before_side_effects(chat_type, handler, telegram_owner) -> None:
    channel = TelegramChannel(TelegramConfig(allow_from=["*"]), MessageBus())
    app = _install_ready_app(channel)
    channel._handle_message = AsyncMock()
    channel._download_message_media = AsyncMock()
    await getattr(channel, handler)(_make_telegram_update(chat_type=chat_type, text="@cirno /stop"), None)
    channel._handle_message.assert_not_awaited()
    channel._download_message_media.assert_not_awaited()
    assert app.bot.get_me_calls == 0


@pytest.mark.asyncio
async def test_private_message_uses_cirno_session(personal_owner) -> None:
    bus = MessageBus()
    channel = TelegramChannel(TelegramConfig(allow_from=["*"]), bus)
    _install_ready_app(channel)
    channel.presence.start_typing = lambda _: None
    channel.presence.add_reaction = AsyncMock()
    await channel._on_message(_make_telegram_update(text="Hello Cirno"), None)
    msg = await bus.consume_inbound()
    assert msg.session_key == "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"
    assert msg.channel == "telegram"
    assert msg.chat_id == "12345"
    assert msg.metadata["webui_turn_id"].startswith("telegram:")


@pytest.mark.asyncio
async def test_extract_reply_context_no_reply() -> None:
    """When there is no reply_to_message, _extract_reply_context returns None."""
    channel = TelegramChannel(TelegramConfig(enabled=True, token="123:abc"), MessageBus())
    message = SimpleNamespace(reply_to_message=None)
    assert await channel._extract_reply_context(message) is None


@pytest.mark.asyncio
async def test_extract_reply_context_with_text(telegram_owner) -> None:
    """When reply has text, return prefixed string."""
    channel = TelegramChannel(TelegramConfig(enabled=True, token="123:abc"), MessageBus())
    _install_ready_app(channel)
    reply = SimpleNamespace(text="Hello world", caption=None, from_user=SimpleNamespace(id=2, username="testuser", first_name="Test"))
    message = SimpleNamespace(reply_to_message=reply)
    assert await channel._extract_reply_context(message) == "[Reply to @testuser: Hello world]"


@pytest.mark.asyncio
async def test_extract_reply_context_with_caption_only(telegram_owner) -> None:
    """When reply has only caption (no text), caption is used."""
    channel = TelegramChannel(TelegramConfig(enabled=True, token="123:abc"), MessageBus())
    _install_ready_app(channel)
    reply = SimpleNamespace(text=None, caption="Photo caption", from_user=SimpleNamespace(id=2, username=None, first_name="Test"))
    message = SimpleNamespace(reply_to_message=reply)
    assert await channel._extract_reply_context(message) == "[Reply to Test: Photo caption]"


@pytest.mark.asyncio
async def test_extract_reply_context_truncation(telegram_owner) -> None:
    """Reply text is truncated at TELEGRAM_REPLY_CONTEXT_MAX_LEN."""
    channel = TelegramChannel(TelegramConfig(enabled=True, token="123:abc"), MessageBus())
    _install_ready_app(channel)
    long_text = "x" * (TELEGRAM_REPLY_CONTEXT_MAX_LEN + 100)
    reply = SimpleNamespace(text=long_text, caption=None, from_user=SimpleNamespace(id=2, username=None, first_name=None))
    message = SimpleNamespace(reply_to_message=reply)
    result = await channel._extract_reply_context(message)
    assert result is not None
    assert result.startswith("[Reply to: ")
    assert result.endswith("...]")
    assert len(result) == len("[Reply to: ]") + TELEGRAM_REPLY_CONTEXT_MAX_LEN + len("...")


@pytest.mark.asyncio
async def test_extract_reply_context_no_text_returns_none() -> None:
    """When reply has no text/caption, _extract_reply_context returns None (media handled separately)."""
    channel = TelegramChannel(TelegramConfig(enabled=True, token="123:abc"), MessageBus())
    reply = SimpleNamespace(text=None, caption=None)
    message = SimpleNamespace(reply_to_message=reply)
    assert await channel._extract_reply_context(message) is None


@pytest.mark.asyncio
async def test_on_message_includes_reply_context(personal_owner) -> None:
    """When user replies to a message, content passed to bus starts with reply context."""
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    handled = []
    async def capture_handle(**kwargs) -> None:
        handled.append(kwargs)
    channel._handle_message = capture_handle
    channel.presence.start_typing = lambda _chat_id: None

    reply = SimpleNamespace(text="Hello", message_id=2, from_user=SimpleNamespace(id=1))
    update = _make_telegram_update(text="translate this", reply_to_message=reply)
    await channel._on_message(update, None)

    assert len(handled) == 1
    assert handled[0]["content"].startswith("[Reply to: Hello]")
    assert "translate this" in handled[0]["content"]


@pytest.mark.asyncio
async def test_download_message_media_returns_path_when_download_succeeds(
    monkeypatch, tmp_path
, telegram_owner) -> None:
    """_download_message_media returns (paths, content_parts) when bot.get_file and download succeed."""
    media_dir = tmp_path / "media" / "telegram"
    media_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "cirno_server.channels.telegram.runtime.get_media_dir",
        lambda channel=None: media_dir if channel else tmp_path / "media",
    )

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.get_file = AsyncMock(
        return_value=SimpleNamespace(download_to_drive=AsyncMock(return_value=None))
    )

    msg = SimpleNamespace(
        photo=[SimpleNamespace(file_id="fid123", mime_type="image/jpeg")],
        voice=None,
        audio=None,
        document=None,
        video=None,
        video_note=None,
        animation=None,
    )
    paths, parts = await channel._download_message_media(msg)
    assert len(paths) == 1
    assert len(parts) == 1
    assert "fid123" in paths[0]
    assert "[image:" in parts[0]


@pytest.mark.asyncio
async def test_download_message_media_uses_file_unique_id_when_available(
    monkeypatch, tmp_path
) -> None:
    media_dir = tmp_path / "media" / "telegram"
    media_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "cirno_server.channels.telegram.runtime.get_media_dir",
        lambda channel=None: media_dir if channel else tmp_path / "media",
    )

    downloaded: dict[str, str] = {}

    async def _download_to_drive(path: str) -> None:
        downloaded["path"] = path

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    app = _FakeApp(lambda: None)
    app.bot.get_file = AsyncMock(
        return_value=SimpleNamespace(download_to_drive=_download_to_drive)
    )
    channel.connection.app = app

    msg = SimpleNamespace(
        photo=[
            SimpleNamespace(
                file_id="file-id-that-should-not-be-used",
                file_unique_id="stable-unique-id",
                mime_type="image/jpeg",
                file_name=None,
            )
        ],
        voice=None,
        audio=None,
        document=None,
        video=None,
        video_note=None,
        animation=None,
    )

    paths, parts = await channel._download_message_media(msg)

    assert downloaded["path"].endswith("stable-unique-id.jpg")
    assert paths == [str(media_dir / "stable-unique-id.jpg")]
    assert parts == [f"[image: {media_dir / 'stable-unique-id.jpg'}]"]


@pytest.mark.asyncio
async def test_on_message_attaches_reply_to_media_when_available(monkeypatch, tmp_path, personal_owner) -> None:
    """When user replies to a message with media, that media is downloaded and attached to the turn."""
    media_dir = tmp_path / "media" / "telegram"
    media_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "cirno_server.channels.telegram.runtime.get_media_dir",
        lambda channel=None: media_dir if channel else tmp_path / "media",
    )

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    app = _FakeApp(lambda: None)
    app.bot.get_file = AsyncMock(
        return_value=SimpleNamespace(download_to_drive=AsyncMock(return_value=None))
    )
    channel.connection.app = app
    handled = []
    async def capture_handle(**kwargs) -> None:
        handled.append(kwargs)
    channel._handle_message = capture_handle
    channel.presence.start_typing = lambda _chat_id: None

    reply_with_photo = SimpleNamespace(
        text=None,
        caption=None,
        photo=[SimpleNamespace(file_id="reply_photo_fid", mime_type="image/jpeg")],
        document=None,
        voice=None,
        audio=None,
        video=None,
        video_note=None,
        animation=None,
    )
    update = _make_telegram_update(
        text="what is the image?",
        reply_to_message=reply_with_photo,
    )
    await channel._on_message(update, None)

    assert len(handled) == 1
    assert handled[0]["content"].startswith("[Reply to: [image:")
    assert "what is the image?" in handled[0]["content"]
    assert len(handled[0]["media"]) == 1
    assert "reply_photo_fid" in handled[0]["media"][0]


@pytest.mark.asyncio
async def test_on_message_reply_to_media_fallback_when_download_fails(personal_owner) -> None:
    """When reply has media but download fails, no media attached and no reply tag."""
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.get_file = None
    handled = []
    async def capture_handle(**kwargs) -> None:
        handled.append(kwargs)
    channel._handle_message = capture_handle
    channel.presence.start_typing = lambda _chat_id: None

    reply_with_photo = SimpleNamespace(
        text=None,
        caption=None,
        photo=[SimpleNamespace(file_id="x", mime_type="image/jpeg")],
        document=None,
        voice=None,
        audio=None,
        video=None,
        video_note=None,
        animation=None,
    )
    update = _make_telegram_update(text="what is this?", reply_to_message=reply_with_photo)
    await channel._on_message(update, None)

    assert len(handled) == 1
    assert "what is this?" in handled[0]["content"]
    assert handled[0]["media"] == []


@pytest.mark.asyncio
async def test_on_message_reply_to_caption_and_media(monkeypatch, tmp_path, personal_owner) -> None:
    """When replying to a message with caption + photo, both text context and media are included."""
    media_dir = tmp_path / "media" / "telegram"
    media_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "cirno_server.channels.telegram.runtime.get_media_dir",
        lambda channel=None: media_dir if channel else tmp_path / "media",
    )

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    app = _FakeApp(lambda: None)
    app.bot.get_file = AsyncMock(
        return_value=SimpleNamespace(download_to_drive=AsyncMock(return_value=None))
    )
    channel.connection.app = app
    handled = []
    async def capture_handle(**kwargs) -> None:
        handled.append(kwargs)
    channel._handle_message = capture_handle
    channel.presence.start_typing = lambda _chat_id: None

    reply_with_caption_and_photo = SimpleNamespace(
        text=None,
        caption="A cute cat",
        photo=[SimpleNamespace(file_id="cat_fid", mime_type="image/jpeg")],
        document=None,
        voice=None,
        audio=None,
        video=None,
        video_note=None,
        animation=None,
    )
    update = _make_telegram_update(
        text="what breed is this?",
        reply_to_message=reply_with_caption_and_photo,
    )
    await channel._on_message(update, None)

    assert len(handled) == 1
    assert "[Reply to: A cute cat]" in handled[0]["content"]
    assert "what breed is this?" in handled[0]["content"]
    assert len(handled[0]["media"]) == 1
    assert "cat_fid" in handled[0]["media"][0]


@pytest.mark.asyncio
async def test_forward_command_does_not_inject_reply_context(personal_owner) -> None:
    """Slash commands forwarded via _forward_command must not include reply context."""
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    handled = []
    async def capture_handle(**kwargs) -> None:
        handled.append(kwargs)
    channel._handle_message = capture_handle

    reply = SimpleNamespace(text="some old message", message_id=2, from_user=SimpleNamespace(id=1))
    update = _make_telegram_update(text="/new", reply_to_message=reply)
    await channel._forward_command(update, None)

    assert len(handled) == 1
    assert handled[0]["content"] == "/new"


@pytest.mark.asyncio
@pytest.mark.parametrize("separator", [" ", "\t", "\n", "\r\n", "  \n"])
@pytest.mark.parametrize("suffix", ["", "@cirno_test"])
async def test_forward_command_preserves_whitespace_and_argument_mentions(separator, suffix, personal_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    handled = []

    async def capture_handle(**kwargs) -> None:
        handled.append(kwargs)

    channel._handle_message = capture_handle
    arguments = "contact@example.org\nkeep the second line"
    text = f"/dream_prompt{suffix}{separator}{arguments}"
    await channel._forward_command(_make_telegram_update(text=text), None)

    assert handled[0]["content"] == f"/dream-prompt{separator}{arguments}"


@pytest.mark.parametrize("text", ["/goal@cirno_test\nfirst\nsecond", "/dream_prompt first\nsecond"])
def test_bus_command_regex_accepts_multiline_arguments(text) -> None:
    assert TelegramChannel.TELEGRAM_BUS_SLASH_COMMAND_RE.fullmatch(text)


@pytest.mark.asyncio
async def test_forward_command_preserves_dream_log_args_and_strips_bot_suffix(personal_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    handled = []

    async def capture_handle(**kwargs) -> None:
        handled.append(kwargs)

    channel._handle_message = capture_handle
    update = _make_telegram_update(text="/dream-log@cirno_test deadbeef", reply_to_message=None)

    await channel._forward_command(update, None)

    assert len(handled) == 1
    assert handled[0]["content"] == "/dream-log deadbeef"


@pytest.mark.asyncio
async def test_forward_command_normalizes_telegram_safe_dream_aliases(personal_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    handled = []

    async def capture_handle(**kwargs) -> None:
        handled.append(kwargs)

    channel._handle_message = capture_handle
    update = _make_telegram_update(text="/dream_restore@cirno_test deadbeef", reply_to_message=None)

    await channel._forward_command(update, None)

    assert len(handled) == 1
    assert handled[0]["content"] == "/dream-restore deadbeef"

    handled.clear()
    update = _make_telegram_update(text="/dream_prompt@cirno_test init", reply_to_message=None)

    await channel._forward_command(update, None)

    assert len(handled) == 1
    assert handled[0]["content"] == "/dream-prompt init"


def test_telegram_bus_slash_command_regex_matches_agent_loop_commands() -> None:
    """Bus-routed slash commands must match the Telegram handler regex (see builtin router)."""
    pat = TelegramChannel.TELEGRAM_BUS_SLASH_COMMAND_RE
    assert pat.fullmatch("/history")
    assert pat.fullmatch("/history 5")
    assert pat.fullmatch("/goal ship the feature")
    assert pat.fullmatch("/trigger")
    assert pat.fullmatch("/trigger PR review")
    assert pat.fullmatch("/pairing list")
    assert pat.fullmatch("/model fast")
    assert pat.fullmatch("/skill")
    assert pat.fullmatch("/skill@cirno_bot")
    assert pat.fullmatch("/new@cirno_bot")
    assert pat.fullmatch("/goal@cirno_bot refine objective")
    assert pat.fullmatch("/trigger@cirno_bot CI summary")
    assert pat.fullmatch("/compact@cirno_bot")
    assert pat.fullmatch("/dream_log deadbeef")
    assert pat.fullmatch("/dream_restore deadbeef")
    assert pat.fullmatch("/dream_prompt init")
    assert not pat.fullmatch("/evaluator_prompt@cirno_bot init")
    assert pat.fullmatch("/unknown-command") is None
    assert pat.fullmatch("/compact")
    assert not pat.fullmatch("/evaluator-prompt")
    assert not pat.fullmatch("/evaluator-prompt init")
    assert pat.fullmatch("/dream-log deadbeef") is None
    assert pat.fullmatch("/dream-restore deadbeef") is None
    assert pat.fullmatch("/dream-prompt init") is None


@pytest.mark.asyncio
async def test_on_help_includes_restart_command(personal_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    update = _make_telegram_update(text="/help", chat_type="private")
    update.message.reply_text = AsyncMock()

    await channel._on_help(update, None)

    update.message.reply_text.assert_awaited_once()
    help_text = update.message.reply_text.await_args.args[0]
    assert "/restart" in help_text
    assert "/status" in help_text
    assert "/skill" in help_text
    assert "/consolidate" in help_text
    assert "/dream_log" in help_text
    assert "/dream_prompt" not in help_text
    assert "/evaluator_prompt" not in help_text
    assert "/compact" not in help_text
    assert "/goal" in help_text
    assert "/trigger" in help_text
    assert "/pairing" not in help_text
    assert "/model" in help_text
    assert "/dream_restore" in help_text


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["dream-log", "dream-restore", "dream-prompt"])
@pytest.mark.parametrize("underscore", [False, True])
async def test_telegram_command_handlers_preserve_core_names(monkeypatch, command, underscore, personal_owner):
    from cirno_server.channels.telegram.binding import TelegramBinding
    binding = TelegramBinding()
    pin = binding.issue_pin()
    assert binding.verify(pin["pin"], user_id=123, chat_id=123)
    bus = MessageBus()
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"), bus,
    )
    app = _FakeApp(lambda: None)
    monkeypatch.setattr("cirno_server.channels.telegram.runtime.HTTPXRequest", _FakeHTTPXRequest)
    monkeypatch.setattr(
        "cirno_server.channels.telegram.runtime.Application",
        SimpleNamespace(builder=lambda: _FakeBuilder(app)),
    )
    await channel._start_app()
    try:
        spelling = command.replace("-", "_") if underscore else command
        text = f"/{spelling}@cirno_test argument"
        update = telegram.Update.de_json({
            "update_id": 1,
            "message": {
                "message_id": 1, "date": 1,
                "chat": {"id": 123, "type": "private"},
                "from": {"id": 123, "is_bot": False, "first_name": "Tester"},
                "text": text,
                "entities": [{
                    "type": "bot_command", "offset": 0,
                    "length": len(text.split()[0]) if underscore else len(command.split("-")[0]) + 1,
                }],
            },
        }, None)
        handler = next(handler for handler in app.handlers if handler.check_update(update))
        assert handler.callback == channel._forward_command
        await handler.callback(update, None)
        message = await asyncio.wait_for(bus.consume_inbound(), timeout=1)
        assert message.content == f"/{command} argument"
    finally:
        await channel._teardown_app()


def test_telegram_command_text_preserves_arguments_paths_and_diffs():
    text = (
        "Use `/dream-log deadbeef` or `/evaluator-prompt init`.\n"
        "Usage: /dream-prompt [init]\n"
        "Keep /tmp/dream-log and /dream-log.md.\n"
        "```diff\n- /dream-log\n+ /dream-prompt\n```\n"
    )
    assert telegram_command_text(text) == (
        "Use /dream_log deadbeef or `/evaluator-prompt init`.\n"
        "Usage: /dream_prompt [init]\n"
        "Keep /tmp/dream-log and /dream-log.md.\n"
        "```diff\n- /dream-log\n+ /dream-prompt\n```\n"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("control_reply", [False, True])
async def test_send_adapts_command_references_only_in_control_replies(control_reply, telegram_owner):
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", rich_messages=False),
        MessageBus(),
    )
    app = _install_ready_app(channel)
    content = "Use `/dream-restore deadbeef`."
    message = OutboundMessage(
        channel="telegram", chat_id="123", content=content,
        metadata={"render_as": "text"} if control_reply else {},
    )
    await channel.send(message)
    expected = "Use /dream_restore deadbeef." if control_reply else markdown_to_telegram_html(content)
    assert app.bot.sent_messages[-1]["text"] == expected
    assert message.content == content


@pytest.mark.asyncio
async def test_on_message_location_content(personal_owner) -> None:
    """Location messages are forwarded as [location: lat, lon] content."""
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    handled = []
    async def capture_handle(**kwargs) -> None:
        handled.append(kwargs)
    channel._handle_message = capture_handle
    channel.presence.start_typing = lambda _chat_id: None

    location = SimpleNamespace(latitude=48.8566, longitude=2.3522)
    update = _make_telegram_update(location=location)
    await channel._on_message(update, None)

    assert len(handled) == 1
    assert handled[0]["content"] == "[location: 48.8566, 2.3522]"


@pytest.mark.asyncio
async def test_on_message_location_with_text(personal_owner) -> None:
    """Location messages with accompanying text include both in content."""
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    handled = []
    async def capture_handle(**kwargs) -> None:
        handled.append(kwargs)
    channel._handle_message = capture_handle
    channel.presence.start_typing = lambda _chat_id: None

    location = SimpleNamespace(latitude=51.5074, longitude=-0.1278)
    update = _make_telegram_update(text="meet me here", location=location)
    await channel._on_message(update, None)

    assert len(handled) == 1
    assert "meet me here" in handled[0]["content"]
    assert "[location: 51.5074, -0.1278]" in handled[0]["content"]


# ---------------------------------------------------------------------------
# Tests for retry amplification fix (issue #3050)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_call_with_retry_accepts_timedelta_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from telegram.error import RetryAfter

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    attempts = 0

    async def retry_once() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RetryAfter(timedelta(seconds=1.5))
        return "ok"

    sleep = AsyncMock()
    monkeypatch.setenv("PTB_TIMEDELTA", "1")
    monkeypatch.setattr(
        "cirno_server.channels.telegram.runtime.asyncio.sleep",
        sleep,
    )

    assert await channel.api.call_with_retry(retry_once) == "ok"
    sleep.assert_awaited_once_with(1.5)


@pytest.mark.asyncio
async def test_send_text_does_not_fallback_on_network_timeout(telegram_owner) -> None:
    """TimedOut should propagate immediately, NOT trigger plain-text fallback.

    Before the fix, _send_text caught ALL exceptions (including TimedOut)
    and retried as plain text, doubling connection demand during pool
    exhaustion — see issue #3050.
    """
    from telegram.error import TimedOut

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)

    call_count = 0

    async def always_timeout(**kwargs):
        nonlocal call_count
        call_count += 1
        raise TimedOut()

    channel.connection.app.bot.send_message = always_timeout

    import cirno_server.channels.telegram.api as tg_mod
    orig_delay = tg_mod._SEND_RETRY_BASE_DELAY
    tg_mod._SEND_RETRY_BASE_DELAY = 0.01
    try:
        with pytest.raises(TimedOut):
            await channel.api.send_text(123, "hello", None, {})
    finally:
        tg_mod._SEND_RETRY_BASE_DELAY = orig_delay

    # A timeout may follow delivery. Neither HTML retry nor plain fallback is safe.
    assert call_count == 1


@pytest.mark.asyncio
async def test_send_text_does_not_fallback_on_network_error(telegram_owner) -> None:
    """NetworkError should propagate immediately, NOT trigger plain-text fallback."""
    from telegram.error import NetworkError

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)

    call_count = 0

    async def always_network_error(**kwargs):
        nonlocal call_count
        call_count += 1
        raise NetworkError("Connection reset")

    channel.connection.app.bot.send_message = always_network_error

    import cirno_server.channels.telegram.api as tg_mod
    orig_delay = tg_mod._SEND_RETRY_BASE_DELAY
    tg_mod._SEND_RETRY_BASE_DELAY = 0.01
    try:
        with pytest.raises(NetworkError):
            await channel.api.send_text(123, "hello", None, {})
    finally:
        tg_mod._SEND_RETRY_BASE_DELAY = orig_delay

    # _call_with_retry does NOT retry NetworkError (only TimedOut/RetryAfter),
    # so it raises after 1 attempt. The fix prevents plain-text fallback.
    # Before the fix: 1 HTML + 1 plain = 2. After the fix: 1 HTML only.
    assert call_count == 1, (
        f"Expected 1 call (HTML only, no plain fallback), got {call_count}"
    )


@pytest.mark.asyncio
async def test_send_text_falls_back_on_bad_request(telegram_owner) -> None:
    """BadRequest (HTML parse error) should still trigger plain-text fallback."""
    from telegram.error import BadRequest

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)

    original_send = channel.connection.app.bot.send_message
    html_call_count = 0

    async def html_fails(**kwargs):
        nonlocal html_call_count
        if kwargs.get("parse_mode") == "HTML":
            html_call_count += 1
            raise BadRequest("Can't parse entities")
        return await original_send(**kwargs)

    channel.connection.app.bot.send_message = html_fails

    import cirno_server.channels.telegram.api as tg_mod
    orig_delay = tg_mod._SEND_RETRY_BASE_DELAY
    tg_mod._SEND_RETRY_BASE_DELAY = 0.01
    try:
        await channel.api.send_text(123, "hello **world**", None, {})
    finally:
        tg_mod._SEND_RETRY_BASE_DELAY = orig_delay

    # HTML attempt failed with BadRequest → fallback to plain text succeeds.
    assert html_call_count == 1, f"Expected 1 HTML attempt, got {html_call_count}"
    assert len(channel.connection.app.bot.sent_messages) == 1
    # Plain text send should NOT have parse_mode
    assert channel.connection.app.bot.sent_messages[0].get("parse_mode") is None


@pytest.mark.asyncio
async def test_send_text_bad_request_plain_fallback_exhausted(telegram_owner) -> None:
    """When both HTML and plain-text fallback fail with BadRequest, the error propagates."""
    from telegram.error import BadRequest

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)

    call_count = 0

    async def always_bad_request(**kwargs):
        nonlocal call_count
        call_count += 1
        raise BadRequest("Bad request")

    channel.connection.app.bot.send_message = always_bad_request

    import cirno_server.channels.telegram.api as tg_mod
    orig_delay = tg_mod._SEND_RETRY_BASE_DELAY
    tg_mod._SEND_RETRY_BASE_DELAY = 0.01
    try:
        with pytest.raises(BadRequest):
            await channel.api.send_text(123, "hello", None, {})
    finally:
        tg_mod._SEND_RETRY_BASE_DELAY = orig_delay

    # _call_with_retry does NOT retry BadRequest (only TimedOut/RetryAfter),
    # so HTML fails after 1 attempt → fallback to plain also fails after 1 attempt.
    # Before the fix: 2 total. After the fix: still 2 (BadRequest SHOULD fallback).
    assert call_count == 2, f"Expected 2 calls (1 HTML + 1 plain), got {call_count}"


# ---------------------------------------------------------------------------
# markdown_to_telegram_html formatting tests
# ---------------------------------------------------------------------------

def test_markdown_to_html_headers_become_bold() -> None:
    from cirno_server.channels.telegram.formatting import markdown_to_telegram_html

    assert markdown_to_telegram_html("# Title") == "<b>Title</b>"
    assert markdown_to_telegram_html("## Subtitle") == "<b>Subtitle</b>"
    assert markdown_to_telegram_html("### Deep") == "<b>Deep</b>"


def test_markdown_to_html_tilde_fence_is_code() -> None:
    from cirno_server.channels.telegram.formatting import markdown_to_telegram_html

    text = "Run:\n~~~python\n# setup\ndef __init__(self): pass\n~~~\nDone"
    assert markdown_to_telegram_html(text) == (
        "Run:\n<pre><code># setup\ndef __init__(self): pass\n</code></pre>\nDone"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("fence", ["~~~", "````"])
async def test_send_preserves_fenced_code_and_escapes_html(fence, telegram_owner) -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    await channel.send(OutboundMessage(
        channel="telegram", chat_id="123",
        content=f"{fence}python\n# setup\na < b && __raw__\n{fence}",
    ))
    assert len(channel.connection.app.bot.sent_messages) == 1
    sent = channel.connection.app.bot.sent_messages[0]
    assert sent["parse_mode"] == "HTML"
    assert sent["text"] == "<pre><code># setup\na &lt; b &amp;&amp; __raw__\n</code></pre>"


def test_markdown_to_html_longer_fence_keeps_nested_example() -> None:
    from cirno_server.channels.telegram.formatting import markdown_to_telegram_html

    text = "Example:\n````markdown\n```python\nx = a * b\n```\n**raw**\n````\nAfter **bold**"
    assert markdown_to_telegram_html(text) == (
        "Example:\n<pre><code>```python\nx = a * b\n```\n**raw**\n</code></pre>\n"
        "After <b>bold</b>"
    )


def test_markdown_to_html_single_line_and_backtick_fences_unchanged() -> None:
    from cirno_server.channels.telegram.formatting import markdown_to_telegram_html

    assert markdown_to_telegram_html("```py\n# c\nx = __y__\n```") == (
        "<pre><code># c\nx = __y__\n</code></pre>"
    )
    assert markdown_to_telegram_html("Use ```ls -la``` now") == "Use <pre><code>ls -la</code></pre> now"


def test_markdown_to_html_numbered_lists_preserved() -> None:
    from cirno_server.channels.telegram.formatting import markdown_to_telegram_html

    text = "1. First\n2. Second\n3. Third"
    result = markdown_to_telegram_html(text)
    assert "1. First" in result
    assert "2. Second" in result
    assert "3. Third" in result


def test_markdown_to_html_numbered_list_normalizes_whitespace() -> None:
    from cirno_server.channels.telegram.formatting import markdown_to_telegram_html

    # Extra spaces after dot should be normalized
    text = "1.   Lots of space\n2.  Two spaces"
    result = markdown_to_telegram_html(text)
    assert "1. Lots of space" in result
    assert "2. Two spaces" in result


def test_markdown_to_html_headers_survive_html_escaping() -> None:
    """Headers containing special HTML chars should still render as bold."""
    from cirno_server.channels.telegram.formatting import markdown_to_telegram_html

    result = markdown_to_telegram_html("# A < B & C > D")
    assert "<b>A &lt; B &amp; C &gt; D</b>" == result


def test_markdown_to_html_mixed_formatting() -> None:
    """Headers, bullets, numbered lists, and bold coexist correctly."""
    from cirno_server.channels.telegram.formatting import markdown_to_telegram_html

    text = "# Overview\n\n- bullet one\n- bullet two\n\n1. step one\n2. step two\n\n**bold text**"
    result = markdown_to_telegram_html(text)
    assert "<b>Overview</b>" in result
    assert "\u2022 bullet one" in result
    assert "1. step one" in result
    assert "<b>bold text</b>" in result


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        (
            "[init](https://github.com/o/r/blob/main/pkg/__init__.py)",
            '<a href="https://github.com/o/r/blob/main/pkg/__init__.py">init</a>',
        ),
        (
            "see [css](https://example.com/_static_/a.css) ok",
            'see <a href="https://example.com/_static_/a.css">css</a> ok',
        ),
        (
            "[x](https://example.com/a**b**c~~d~~)",
            '<a href="https://example.com/a**b**c~~d~~">x</a>',
        ),
    ],
)
def test_markdown_to_html_link_urls_are_not_formatted(markdown: str, expected: str) -> None:
    """Inline-formatting passes must not inject tags into href attributes."""
    assert markdown_to_telegram_html(markdown) == expected


def test_markdown_to_html_link_url_quotes_are_escaped() -> None:
    result = markdown_to_telegram_html('[q](https://example.com/?q="x"&y=1)')

    assert result == '<a href="https://example.com/?q=&quot;x&quot;&amp;y=1">q</a>'


def test_markdown_to_html_link_text_keeps_formatting() -> None:
    result = markdown_to_telegram_html("[**bold** _it_](https://example.com/a_b_c)")

    assert result == '<a href="https://example.com/a_b_c"><b>bold</b> <i>it</i></a>'


# ---------------------------------------------------------------------------
# strip_md_block tests
# ---------------------------------------------------------------------------

def test_strip_md_block_removes_inline_formatting() -> None:
    from cirno_server.channels.telegram.formatting import strip_md_block

    text = "**bold** and _italic_ and ~~struck~~"
    result = strip_md_block(text)
    assert result == "bold and italic and struck"


def test_strip_md_block_strips_headers() -> None:
    from cirno_server.channels.telegram.formatting import strip_md_block

    assert strip_md_block("## Title\nBody") == "Title\nBody"


def test_strip_md_block_converts_bullets_and_numbers() -> None:
    from cirno_server.channels.telegram.formatting import strip_md_block

    text = "- item a\n1. item b\n2. item c"
    result = strip_md_block(text)
    assert "\u2022 item a" in result
    assert "1. item b" in result
    assert "2. item c" in result


def test_strip_md_block_strips_tilde_fences() -> None:
    from cirno_server.channels.telegram.formatting import strip_md_block

    assert strip_md_block("~~~bash\nls\n~~~\nDone") == "ls\n\nDone"


def test_strip_md_block_strips_links() -> None:
    from cirno_server.channels.telegram.formatting import strip_md_block

    assert strip_md_block("[click here](https://example.com)") == "click here"


# ---------------------------------------------------------------------------
# Streaming mid-edit uses strip_md_block
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_delta_mid_stream_strips_markdown(telegram_owner) -> None:
    """Mid-stream edits should strip markdown so users see clean text."""
    telegram_owner(999)
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=42))
    channel.connection.app.bot.edit_message_text = AsyncMock()

    # Initial send with markdown
    await channel.send_delta("999", "**hello** world")
    sent_text = channel.connection.app.bot.send_message.call_args.kwargs.get("text", "")
    # Should NOT contain raw markdown asterisks
    assert "**" not in sent_text
    assert "hello world" in sent_text

    # Mid-stream edit
    import time
    buf = channel.streams.buffers["999"]
    buf.last_edit = time.monotonic() - 10  # force edit interval
    await channel.send_delta("999", "\n### Title\n1. step")
    edited_text = channel.connection.app.bot.edit_message_text.call_args.kwargs.get("text", "")
    assert "###" not in edited_text
    assert "**" not in edited_text
    assert "Title" in edited_text
    assert "1. step" in edited_text


def test_build_keyboard_respects_inline_keyboards_flag() -> None:
    """``_build_keyboard`` returns ``None`` whenever the feature flag is off,
    regardless of whether buttons are provided; returns a proper Markup only
    when the flag is explicitly enabled. Pins the kill-switch so accidentally
    flipping the default doesn't silently expose callback handlers."""
    from telegram import InlineKeyboardMarkup

    off = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", inline_keyboards=False),
        MessageBus(),
    )
    assert off.delivery.build_keyboard([["A", "B"]]) is None

    on = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", inline_keyboards=True),
        MessageBus(),
    )
    assert on.delivery.build_keyboard([]) is None  # empty still no-op
    markup = on.delivery.build_keyboard([["Yes", "No"], ["Cancel"]])
    assert isinstance(markup, InlineKeyboardMarkup)
    rows = markup.inline_keyboard
    assert [[b.text for b in row] for row in rows] == [["Yes", "No"], ["Cancel"]]
    # callback_data mirrors label so _on_callback_query can echo the tap back.
    assert rows[0][0].callback_data == "Yes"


def test_safe_callback_data_truncates_at_utf8_boundary() -> None:
    # Telegram's 64-byte callback_data cap is a hard API limit; silent 400s were the bug.
    short = "Yes"
    assert TelegramDelivery.safe_callback_data(short) == short

    long_ascii = "a" * 100
    out = TelegramDelivery.safe_callback_data(long_ascii)
    assert len(out.encode("utf-8")) <= 64
    assert long_ascii.startswith(out)

    # Multibyte labels must not split a codepoint mid-byte.
    long_cjk = "同意并继续下一步，我已阅读并同意了服务条款以及隐私政策"
    assert len(long_cjk.encode("utf-8")) > 64
    out = TelegramDelivery.safe_callback_data(long_cjk)
    assert len(out.encode("utf-8")) <= 64
    assert long_cjk.startswith(out)
    out.encode("utf-8").decode("utf-8")  # must round-trip cleanly


def test_build_keyboard_uses_safe_callback_data_for_long_labels() -> None:
    # Pins the integration so a long-label payload survives ``send_message`` instead of 400ing.
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", inline_keyboards=True),
        MessageBus(),
    )
    long_label = "Approve and continue to the next step with the updated terms of service"
    assert len(long_label.encode("utf-8")) > 64

    markup = channel.delivery.build_keyboard([[long_label]])
    btn = markup.inline_keyboard[0][0]
    assert btn.text == long_label  # display preserved
    assert len(btn.callback_data.encode("utf-8")) <= 64
    assert long_label.startswith(btn.callback_data)


def test_buttons_as_text_format_preserves_rows_and_labels() -> None:
    # Canonical shape: one row per line, labels bracketed. Layout survives the fallback.
    assert TelegramDelivery.buttons_as_text([["Yes", "No"], ["Cancel"]]) == "[Yes] [No]\n[Cancel]"
    assert TelegramDelivery.buttons_as_text([["Only"]]) == "[Only]"
    assert TelegramDelivery.buttons_as_text([[], ["A"]]) == "[A]"  # empty rows skipped


@pytest.mark.asyncio
async def test_send_falls_back_buttons_to_inline_text_when_flag_off(telegram_owner) -> None:
    """Buttons are semantic options; with ``inline_keyboards=False`` we must
    splice labels into the text so users still see the choices. Silent-drop
    was the pre-fallback bug — the agent got a success reply while the user
    saw a question with no options."""
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", inline_keyboards=False),
        MessageBus(),
    )
    _install_ready_app(channel)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="123",
            content="Proceed?",
            buttons=[["Yes", "No"], ["Cancel"]],
        )
    )

    assert len(channel.connection.app.bot.sent_messages) == 1
    sent = channel.connection.app.bot.sent_messages[0]
    assert sent.get("reply_markup") is None
    assert "Proceed?" in sent["text"]
    assert "[Yes] [No]" in sent["text"]
    assert "[Cancel]" in sent["text"]


@pytest.mark.asyncio
async def test_send_uses_native_keyboard_when_flag_on(telegram_owner) -> None:
    """With the flag on, the content stays clean and buttons ride in ``reply_markup``."""
    from telegram import InlineKeyboardMarkup

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", inline_keyboards=True),
        MessageBus(),
    )
    _install_ready_app(channel)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="123",
            content="Proceed?",
            buttons=[["Yes", "No"]],
        )
    )

    sent = channel.connection.app.bot.sent_messages[0]
    assert isinstance(sent.get("reply_markup"), InlineKeyboardMarkup)
    assert "[Yes]" not in sent["text"]  # native keyboard owns the rendering


@pytest.mark.asyncio
async def test_callback_query_ignores_unauthorized_user_before_side_effects() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", inline_keyboards=True),
        MessageBus(),
    )
    channel._handle_message = AsyncMock()

    query = SimpleNamespace(
        id="cb_1",
        data="Yes",
        answer=AsyncMock(),
        message=SimpleNamespace(
            chat=SimpleNamespace(id=123, type="private"),
            edit_reply_markup=AsyncMock(),
        ),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=12345, username="alice", first_name="Alice"),
    )

    await channel._on_callback_query(update, None)

    query.answer.assert_not_awaited()
    query.message.edit_reply_markup.assert_not_awaited()
    channel._handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_callback_query_handles_inaccessible_message(personal_owner) -> None:
    from telegram import Chat, InaccessibleMessage

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc", inline_keyboards=True),
        MessageBus(),
    )
    channel._handle_message = AsyncMock()
    channel.presence.start_typing = lambda _chat_id: None

    query = SimpleNamespace(
        id="cb_inaccessible",
        data="Yes",
        answer=AsyncMock(),
        message=InaccessibleMessage(
            chat=Chat(id=123, type="private"),
            message_id=456,
        ),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=12345, username="alice", first_name="Alice"),
    )

    await channel._on_callback_query(update, None)

    query.answer.assert_awaited_once()
    channel._handle_message.assert_awaited_once()
    assert channel._handle_message.await_args.kwargs["chat_id"] == "123"

def test_markdown_to_html_code_block_special_chars_language() -> None:
    from cirno_server.channels.telegram.formatting import (
        markdown_to_telegram_html,
        strip_md_block,
    )

    text = "```c++\nint main() { return 0; }\n```"
    html = markdown_to_telegram_html(text)
    assert html == "<pre><code>int main() { return 0; }\n</code></pre>"

    stripped = strip_md_block(text)
    assert stripped == "int main() { return 0; }\n"
def test_markdown_to_html_code_block_same_line_no_newline() -> None:
    """
    Locks out the regression where triple-backtick content without a newline
    (e.g., Use ```<tag>``` here) was mistaken for a language info string and discarded.
    """
    from cirno_server.channels.telegram.formatting import (
        markdown_to_telegram_html,
        strip_md_block,
    )

    text = "Use ```<tag>``` here"
    html = markdown_to_telegram_html(text)
    assert html == "Use <pre><code>&lt;tag&gt;</code></pre> here"

    stripped = strip_md_block(text)
    assert stripped == "Use <tag> here"


@pytest.mark.asyncio
async def test_send_delta_stream_end_rich_disabled_uses_legacy_html(telegram_owner) -> None:
    """rich_messages=False (the default) keeps the legacy HTML path untouched."""
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.do_api_request = AsyncMock()
    channel.connection.app.bot.edit_message_text = AsyncMock()
    channel.streams.buffers["123"] = StreamBuf(text="hello", message_id=7, last_edit=0.0)

    await channel.send_delta("123", "", stream_end=True)

    channel.connection.app.bot.do_api_request.assert_not_called()
    channel.connection.app.bot.edit_message_text.assert_awaited_once()
    assert "123" not in channel.streams.buffers


# ---------------------------------------------------------------------------
# Compaction notices: started sends, terminal phase edits in place
# ---------------------------------------------------------------------------

def _compaction_message(phase: str, compaction_id: str = "c1") -> OutboundMessage:
    return OutboundMessage(
        channel="telegram",
        chat_id="999",
        content={
            "started": "Compressing context…",
            "succeeded": "Context compacted.",
            "failed": "Unable to compact context.",
            "cancelled": "Context compaction cancelled.",
        }[phase],
        event=ContextCompactionEvent(compaction_id=compaction_id, phase=phase, notify=True),
    )


@pytest.mark.asyncio
async def test_compaction_terminal_phase_edits_started_notice_in_place(telegram_owner) -> None:
    telegram_owner(999)
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=77))
    channel.connection.app.bot.edit_message_text = AsyncMock()

    await channel.send(_compaction_message("started"))

    channel.connection.app.bot.send_message.assert_awaited_once()
    channel.connection.app.bot.edit_message_text.assert_not_awaited()
    assert channel.delivery.compaction.messages[("999", "c1")] == 77

    await channel.send(_compaction_message("succeeded"))

    # The outcome rewrites the original notice instead of posting a new message.
    channel.connection.app.bot.send_message.assert_awaited_once()
    channel.connection.app.bot.edit_message_text.assert_awaited_once_with(
        chat_id=999, message_id=77, text="Context compacted.",
    )
    assert ("999", "c1") not in channel.delivery.compaction.messages


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["started", "succeeded", "failed", "cancelled"])
async def test_automatic_compaction_is_received_but_not_sent(phase, telegram_owner) -> None:
    telegram_owner(999)
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.send_message = AsyncMock()
    channel.presence.stop_typing = Mock()
    channel.presence.remove_reaction = AsyncMock()

    await channel.send(OutboundMessage(
        channel="telegram", chat_id="999", content="Compressing context…",
        metadata={"message_id": "42"},
        event=ContextCompactionEvent(compaction_id="c1", phase=phase),
    ))

    channel.connection.app.bot.send_message.assert_not_awaited()
    channel.presence.stop_typing.assert_not_called()
    channel.presence.remove_reaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_compaction_edit_failure_falls_back_to_new_message(telegram_owner) -> None:
    telegram_owner(999)
    from telegram.error import BadRequest

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=77))
    channel.connection.app.bot.edit_message_text = AsyncMock(
        side_effect=BadRequest("Message to edit not found")
    )

    await channel.send(_compaction_message("started"))
    await channel.send(_compaction_message("failed"))

    assert channel.connection.app.bot.send_message.await_count == 2
    assert channel.delivery.compaction.messages == {}


@pytest.mark.asyncio
async def test_compaction_terminal_phase_without_notice_sends_message(telegram_owner) -> None:
    telegram_owner(999)
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=1))
    channel.connection.app.bot.edit_message_text = AsyncMock()

    await channel.send(_compaction_message("cancelled"))

    channel.connection.app.bot.edit_message_text.assert_not_awaited()
    channel.connection.app.bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_compaction_notices_are_tracked_per_compaction_id(telegram_owner) -> None:
    telegram_owner(999)
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="123:abc"),
        MessageBus(),
    )
    _install_ready_app(channel)
    channel.connection.app.bot.send_message = AsyncMock(
        side_effect=[
            SimpleNamespace(message_id=101),
            SimpleNamespace(message_id=202),
        ]
    )
    channel.connection.app.bot.edit_message_text = AsyncMock()

    await channel.send(_compaction_message("started", compaction_id="c1"))
    await channel.send(_compaction_message("started", compaction_id="c2"))
    await channel.send(_compaction_message("succeeded", compaction_id="c1"))

    channel.connection.app.bot.edit_message_text.assert_awaited_once_with(
        chat_id=999, message_id=101, text="Context compacted.",
    )
    assert channel.delivery.compaction.messages == {("999", "c2"): 202}


@pytest.mark.asyncio
async def test_unbound_private_input_uses_web_pin_without_creating_pairing_request():
    channel = TelegramChannel(TelegramConfig(), MessageBus())
    channel._handle_message = AsyncMock()
    update = _make_telegram_update(text="hello")
    update.message.reply_text = AsyncMock()
    await channel._on_message(update, None)
    channel._handle_message.assert_not_awaited()
    update.message.reply_text.assert_awaited_once()
    assert "Settings → Telegram" in update.message.reply_text.call_args.args[0]
    assert channel.bus.inbound_size == 0
