"""Output helpers for the single-request CLI; no terminal input loop."""
from __future__ import annotations

import sys
from contextlib import nullcontext
from typing import Any

from cirno import __logo__
from cirno.cli.stream import StreamRenderer, ThinkingSpinner
from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text

console = Console()
_REASONING_SENTENCE_ENDINGS = (".", "!", "?", "。", "！", "？")
_REASONING_FLUSH_CHARS = 60

def _make_console() -> Console:
    return Console(file=sys.stdout)


def _print_agent_response(
    response: str,
    render_markdown: bool,
    metadata: dict[str, Any] | None = None,
    show_header: bool = True,
) -> None:
    """Render assistant response with consistent terminal styling."""
    console = _make_console()
    content = response or ""
    body = _response_renderable(content, render_markdown, metadata)
    if show_header:
        console.print()
        console.print(f"[cyan]{__logo__} cirno[/cyan]")
    console.print(body)
    console.print()


def _response_renderable(
    content: str, render_markdown: bool, metadata: dict[str, Any] | None = None
) -> Text | Markdown:
    """Render plain-text command output without markdown collapsing newlines."""
    if not render_markdown:
        return Text(content)
    if (metadata or {}).get("render_as") == "text":
        return Text(content)
    return Markdown(content)


def _print_cli_progress_line(
    text: str,
    thinking: ThinkingSpinner | None,
    renderer: StreamRenderer | None = None,
) -> None:
    """Print a CLI progress line, pausing the spinner if needed."""
    if not text.strip():
        return
    target = renderer.console if renderer else console
    pause = renderer.pause_spinner() if renderer else (thinking.pause() if thinking else nullcontext())
    with pause:
        if renderer:
            renderer.ensure_header()
        target.print(f"  [dim]↳ {text}[/dim]")


class _ReasoningBuffer:
    def __init__(self) -> None:
        self._text = ""

    def add(self, text: str) -> str | None:
        if not text:
            return None
        self._text += text
        if self._should_flush(text):
            return self.flush()
        return None

    def flush(self) -> str | None:
        text = self._text.strip()
        self._text = ""
        return text or None

    def clear(self) -> None:
        self._text = ""

    def _should_flush(self, text: str) -> bool:
        stripped = text.rstrip()
        return (
            "\n" in text
            or stripped.endswith(_REASONING_SENTENCE_ENDINGS)
            or len(self._text) >= _REASONING_FLUSH_CHARS
        )


def _print_cli_reasoning(
    text: str,
    thinking: ThinkingSpinner | None,
    renderer: StreamRenderer | None = None,
) -> None:
    """Print reasoning/thinking content in a distinct style."""
    if not text.strip():
        return
    target = renderer.console if renderer else console
    pause = renderer.pause_spinner() if renderer else (thinking.pause() if thinking else nullcontext())
    with pause:
        if renderer:
            renderer.ensure_header()
        target.print(f"[dim italic]✻ {text}[/dim italic]")


def _flush_cli_reasoning(
    reasoning_buffer: _ReasoningBuffer,
    thinking: ThinkingSpinner | None,
    renderer: StreamRenderer | None = None,
) -> None:
    text = reasoning_buffer.flush()
    if text:
        _print_cli_reasoning(text, thinking, renderer)
