"""Reasoning extraction from tagged and structured model responses."""

from __future__ import annotations

import re
from typing import Any


def _tag_regex(tags: tuple[str, ...]) -> str:
    return rf"(?:{'|'.join(re.escape(tag) for tag in tags)})"


_THINKING_TAGS = ("think", "thinking", "thought")


_THINKING_TAG = _tag_regex(_THINKING_TAGS)


_INLINE_SELF_CLOSING_THINKING_TAG = r"(?:thinking)"


_THINKING_TAG_PREFIX = "|".join(
    sorted(
        {re.escape(tag[:i]) for tag in _THINKING_TAGS for i in range(1, len(tag) + 1)},
        key=len,
        reverse=True,
    )
)


_PARTIAL_THINKING_TAG = rf"</?(?:{_THINKING_TAG_PREFIX})>?"


def strip_think(text: str) -> str:
    """Remove thinking blocks, unclosed trailing tags, and tokenizer-level
    template leaks occasionally emitted by some models (notably Gemma 4's
    Ollama renderer).

    Covers:
      1. Well-formed `<think>...</think>`, `<thinking>...</thinking>`,
         and `<thought>...</thought>` blocks.
      2. Streaming prefixes where the block is never closed.
      3. *Malformed* opening tags missing the `>` — e.g. `<think广场…`. The
         model sometimes emits the tag name directly followed by user-facing
         content with no delimiter; without this step the literal `<think`
         leaks into the rendered message.
      4. Harmony-style channel markers like `<channel|>` / `<|channel|>`
         **at the start of the text** — conservative to avoid eating
         explanatory prose that mentions these tokens.
      5. Orphan closing tags `</think>` / `</thinking>` / `</thought>`
         **at the very start or end of the text** only, for the same reason.
      6. Trailing partial control tags split across stream chunks, such as
         `<thi`, `<thin`, or `<tho`.

    Since this is also applied before persisting to history (memory.py),
    the edge-only stripping of (4) and (5) is deliberate: stripping those
    tokens mid-text would silently rewrite any message where a user or the
    assistant discusses the tokens themselves.
    """
    # Every supported control tag contains '<'; ordinary text only needs trimming.
    if "<" not in text:
        return text.strip()
    # Well-formed blocks first.
    text = re.sub(rf"<(?P<tag>{_THINKING_TAG})>[\s\S]*?</(?P=tag)>", "", text)
    text = re.sub(rf"^\s*<{_THINKING_TAG}>[\s\S]*$", "", text)
    # Self-closing `<thinking/>` is an empty marker, not user-visible text.
    text = re.sub(rf"^\s*<{_INLINE_SELF_CLOSING_THINKING_TAG}/>\s*", "", text)
    text = re.sub(rf"\s*<{_INLINE_SELF_CLOSING_THINKING_TAG}/>\s*$", "", text)
    # Malformed opening tags: `<think` / `<thinking` / `<thought` where the next char is
    # NOT one that could continue a valid tag / identifier name. Explicitly
    # listing ASCII tag-name chars (letters, digits, `_`, `-`, `:`) plus
    # `>` / `/` — we can't use `\w` here because in Python's default
    # Unicode regex mode it matches CJK characters too, which would defeat
    # the primary fix for `<think广场…` leaks.
    text = re.sub(rf"<{_THINKING_TAG}(?![A-Za-z0-9_\-:>/])", "", text)
    # Edge-only orphan closing tags (start or end of text).
    text = re.sub(rf"^\s*</{_THINKING_TAG}>\s*", "", text)
    text = re.sub(rf"\s*</{_THINKING_TAG}>\s*$", "", text)
    # Edge-only channel markers (harmony / Gemma 4 variant leaks).
    text = re.sub(r"^\s*<\|?channel\|?>\s*", "", text)
    # Stream chunks may end in the middle of a control tag. Strip only known
    # control-token prefixes at the very end.
    partial_control_tag = (
        rf"{_PARTIAL_THINKING_TAG}|"
        r"<\|?(?:c|ch|cha|chan|chann|channe|channel)(?:\|?>?)?"
    )
    text = re.sub(rf"(?:{partial_control_tag})$", "", text)
    text = re.sub(r"^\s*<\|?$", "", text)
    return text.strip()


def strip_reasoning_tags(text: object) -> str:
    """Remove wrapper tags from text that is already known to be reasoning."""
    if not isinstance(text, str):
        return ""
    if "<" not in text:
        return text.strip()
    text = re.sub(rf"^\s*<{_THINKING_TAG}/>\s*", "", text)
    text = re.sub(rf"\s*<{_THINKING_TAG}/>\s*$", "", text)
    text = re.sub(rf"^\s*<{_THINKING_TAG}>\s*", "", text)
    text = re.sub(rf"\s*</{_THINKING_TAG}>\s*$", "", text)
    text = re.sub(rf"\s*(?:{_PARTIAL_THINKING_TAG})$", "", text)
    return text.strip()


def extract_think(text: str) -> tuple[str | None, str]:
    """Extract thinking content from inline thinking tags.

    Returns ``(thinking_text, cleaned_text)``. Only closed blocks are
    extracted; unclosed streaming prefixes are stripped from the cleaned
    text but not surfaced — :func:`strip_think` handles that case.
    """
    if "<" not in text:
        return None, text.strip()
    parts: list[str] = []
    for m in re.finditer(rf"<(?P<tag>{_THINKING_TAG})>([\s\S]*?)</(?P=tag)>", text):
        parts.append(m.group(2).strip())
    thinking = "\n\n".join(parts) if parts else None
    return thinking, strip_think(text)


class IncrementalThinkExtractor:
    """Stateful inline ``<think>`` extractor for streaming buffers.

    Streaming providers expose only a single content delta channel. When a
    model embeds reasoning in ``<think>...</think>`` blocks inside that
    channel, callers need to surface the reasoning incrementally as it
    arrives without re-emitting earlier text. This holds the "already
    emitted" cursor so the runner and the loop hook share one shape.
    """

    __slots__ = ("_emitted",)

    def __init__(self) -> None:
        self._emitted = ""

    def reset(self) -> None:
        self._emitted = ""

    async def feed(self, buf: str, emit: Any) -> bool:
        """Emit any new thinking text found in ``buf``.

        Returns True if anything was emitted this call. ``emit`` is an
        async callable taking a single string (typically
        ``hook.emit_reasoning``).
        """
        thinking, _ = extract_think(buf)
        if not thinking or thinking == self._emitted:
            return False
        new = thinking[len(self._emitted) :]
        if not new.strip():
            return False
        self._emitted = thinking
        await emit(new)
        return True


def extract_reasoning(
    reasoning_content: str | None,
    thinking_blocks: list[dict[str, Any]] | None,
    content: str | None,
) -> tuple[str | None, str | None]:
    """Return ``(reasoning_text, cleaned_content)`` from one model response.

    Single source of truth for "what reasoning did this response carry, and
    what answer text remains after we peel it out". Fallback order:

    1. Dedicated ``reasoning_content`` (DeepSeek-R1, Kimi, MiMo, OpenAI
       reasoning models, Bedrock).
    2. Anthropic ``thinking_blocks``.
    3. Inline ``<think>`` / ``<thought>`` blocks in ``content``.

    Only one source contributes per response; lower-priority sources are
    ignored if a higher-priority one is present, but inline ``<think>``
    tags are still stripped from ``content`` so they never leak into the
    final answer.
    """
    if reasoning_content:
        return strip_reasoning_tags(reasoning_content), strip_think(content) if content else content
    if thinking_blocks:
        parts = [
            strip_reasoning_tags(tb.get("thinking", ""))
            for tb in thinking_blocks
            if tb.get("type") == "thinking"
        ]
        joined = "\n\n".join(p for p in parts if p)
        return (joined or None), strip_think(content) if content else content
    if content:
        return extract_think(content)
    return None, content
