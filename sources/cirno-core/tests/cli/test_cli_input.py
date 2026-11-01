from contextlib import nullcontext
from io import StringIO
from unittest.mock import MagicMock, call, patch

import pytest
from cirno.cli import stream as stream_mod
from cirno.cli import terminal


def test_thinking_spinner_pause_stops_and_restarts():
    """Pause should stop the active spinner and restart it afterward."""
    spinner = MagicMock()
    mock_console = MagicMock()
    mock_console.status.return_value = spinner

    thinking = stream_mod.ThinkingSpinner(console=mock_console)
    with thinking:
        with thinking.pause():
            pass

    assert spinner.method_calls == [
        call.start(),
        call.stop(),
        call.start(),
        call.stop(),
    ]


def test_print_cli_progress_line_pauses_spinner_before_printing():
    """CLI progress output should pause spinner to avoid garbled lines."""
    order: list[str] = []
    spinner = MagicMock()
    spinner.start.side_effect = lambda: order.append("start")
    spinner.stop.side_effect = lambda: order.append("stop")
    mock_console = MagicMock()
    mock_console.status.return_value = spinner

    with patch.object(terminal.console, "print", side_effect=lambda *_args, **_kwargs: order.append("print")):
        thinking = stream_mod.ThinkingSpinner(console=mock_console)
        with thinking:
            terminal._print_cli_progress_line("tool running", thinking)

    assert order == ["start", "stop", "print", "start", "stop"]


def test_thinking_spinner_clears_status_line_when_paused():
    """Stopping the spinner should erase its transient line before output."""
    stream = StringIO()
    stream.isatty = lambda: True  # type: ignore[method-assign]
    mock_console = MagicMock()
    mock_console.file = stream
    spinner = MagicMock()
    mock_console.status.return_value = spinner

    thinking = stream_mod.ThinkingSpinner(console=mock_console)
    with thinking:
        with thinking.pause():
            pass

    assert "\r\x1b[2K" in stream.getvalue()


def test_stream_renderer_stops_spinner_even_after_header_printed():
    """A later answer delta must stop the spinner even when header already exists."""
    stream = StringIO()
    stream.isatty = lambda: True  # type: ignore[method-assign]
    mock_console = MagicMock()
    mock_console.file = stream
    spinner = MagicMock()
    mock_console.status.return_value = spinner

    with patch.object(stream_mod, "_make_console", return_value=mock_console):
        renderer = stream_mod.StreamRenderer(show_spinner=True)
        renderer._header_printed = True
        renderer.ensure_header()

    spinner.stop.assert_called_once()
    assert "\r\x1b[2K" in stream.getvalue()


def test_print_cli_progress_line_opens_renderer_header_before_trace():
    """Trace lines should appear under the assistant header, not under You."""
    order: list[str] = []
    renderer = MagicMock()
    renderer.console.print.side_effect = lambda *_args, **_kwargs: order.append("print")
    renderer.ensure_header.side_effect = lambda: order.append("header")
    renderer.pause_spinner.return_value = nullcontext()

    terminal._print_cli_progress_line("tool running", None, renderer)

    assert order == ["header", "print"]


def test_print_cli_progress_line_stops_live_before_trace():
    """A trace line should not leak the current transient Live frame."""
    mock_live = MagicMock()
    renderer = stream_mod.StreamRenderer(show_spinner=False)
    renderer._live = mock_live

    terminal._print_cli_progress_line("tool running", None, renderer)

    mock_live.stop.assert_called_once()
    assert renderer._live is None


def test_response_renderable_uses_text_for_explicit_plain_rendering():
    status = (
        "🐈 cirno v0.1.4.post5\n"
        "🧠 Model: MiniMax-M2.7\n"
        "📊 Tokens: 20639 in / 29 out"
    )

    renderable = terminal._response_renderable(
        status,
        render_markdown=True,
        metadata={"render_as": "text"},
    )

    assert renderable.__class__.__name__ == "Text"


def test_response_renderable_preserves_normal_markdown_rendering():
    renderable = terminal._response_renderable("**bold**", render_markdown=True)

    assert renderable.__class__.__name__ == "Markdown"


def test_response_renderable_without_metadata_keeps_markdown_path():
    help_text = "🐈 cirno commands:\n/status — Show bot status\n/help — Show available commands"

    renderable = terminal._response_renderable(help_text, render_markdown=True)

    assert renderable.__class__.__name__ == "Markdown"


@pytest.mark.asyncio
async def test_on_end_writes_final_content_to_stdout_after_stopping_live():
    """on_end should stop Live (transient erases it) then print final content to stdout."""
    mock_live = MagicMock()
    mock_console = MagicMock()
    mock_console.capture.return_value.__enter__ = MagicMock(
        return_value=MagicMock(get=lambda: "final output\n")
    )
    mock_console.capture.return_value.__exit__ = MagicMock(return_value=False)

    with patch.object(stream_mod, "_make_console", return_value=mock_console):
        renderer = stream_mod.StreamRenderer(show_spinner=False)
        renderer._live = mock_live
        renderer._buf = "final output"

        written: list[str] = []
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.write = lambda s: written.append(s)
            mock_stdout.flush = MagicMock()
            await renderer.on_end()

    mock_live.stop.assert_called_once()
    assert renderer._live is None
    assert written == ["final output\n"]


@pytest.mark.asyncio
async def test_on_end_resuming_clears_buffer_and_restarts_spinner():
    """on_end(resuming=True) should reset state for the next iteration."""
    spinner = MagicMock()
    mock_console = MagicMock()
    mock_console.status.return_value = spinner
    mock_console.capture.return_value.__enter__ = MagicMock(
        return_value=MagicMock(get=lambda: "")
    )
    mock_console.capture.return_value.__exit__ = MagicMock(return_value=False)

    with patch.object(stream_mod, "_make_console", return_value=mock_console):
        renderer = stream_mod.StreamRenderer(show_spinner=True)
        renderer._buf = "some content"

        await renderer.on_end(resuming=True)

    assert renderer._buf == ""
    # Spinner should have been restarted (start called twice: __init__ + resuming)
    assert spinner.start.call_count == 2


def test_make_console_force_terminal_when_stdout_is_tty():
    """Console should set force_terminal=True when stdout is a TTY (rich output)."""
    import sys
    with patch.object(sys.stdout, "isatty", return_value=True):
        console = stream_mod._make_console()
        assert console._force_terminal is True


def test_make_console_force_terminal_false_when_stdout_is_not_tty():
    """Console should set force_terminal=False when stdout is not a TTY so that
    ANSI escape codes (cursor visibility, braille spinner frames) don't pollute
    piped output such as `docker exec -i` (#3265)."""
    import sys
    with patch.object(sys.stdout, "isatty", return_value=False):
        console = stream_mod._make_console()
        assert console._force_terminal is False


