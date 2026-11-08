"""Unicode-safe text splitting and bounded truncation."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, TypeVar, cast, overload

from cirno_core.utils import token_encoding

_T = TypeVar("_T")


@overload
def sanitize_surrogates(text: str) -> str: ...


@overload
def sanitize_surrogates(text: _T) -> _T: ...


def sanitize_surrogates(text: Any) -> Any:
    """Reconstruct surrogate pairs and replace unpaired surrogates.

    Lone UTF-16 surrogate code points (``U+D800``..``U+DFFF``) cannot be
    encoded as UTF-8 and cause ``UnicodeEncodeError`` when the message is
    serialized for an HTTP request body. This helper round-trips through
    UTF-16 to reconstruct genuine surrogate pairs (produced e.g. by Windows
    console input for emoji) and substitutes lone surrogates with
    ``U+FFFD``.

    Non-string inputs are returned unchanged so this helper is safe to call
    on arbitrary message payload leaves.
    """
    if not isinstance(text, str):
        return text
    # Fast path: no surrogate code points → return the original object so
    # callers can rely on identity to detect an actual mutation.
    for ch in text:
        cp = ord(ch)
        if 0xD800 <= cp <= 0xDFFF:
            break
    else:
        return text
    return text.encode("utf-16-le", errors="surrogatepass").decode("utf-16-le", errors="replace")


def sanitize_surrogates_deep(value: Any) -> Any:
    """Recursively apply :func:`sanitize_surrogates` to every string leaf.

    Lists and dicts are rebuilt only when a nested string actually changes,
    so the common case (no surrogates present) returns the original object
    without allocations.
    """
    if isinstance(value, str):
        cleaned = sanitize_surrogates(value)
        return cleaned
    if isinstance(value, list):
        result_list: list[Any] = []
        mutated = False
        for item in cast(list[Any], value):
            new_item = sanitize_surrogates_deep(item)
            if new_item is not item:
                mutated = True
            result_list.append(new_item)
        return result_list if mutated else cast(Any, value)
    if isinstance(value, dict):
        result_dict: dict[Any, Any] = {}
        mutated = False
        for key, item in cast(dict[Any, Any], value).items():
            new_item = sanitize_surrogates_deep(item)
            if new_item is not item:
                mutated = True
            result_dict[key] = new_item
        return result_dict if mutated else cast(Any, value)
    if isinstance(value, tuple):
        tuple_value = cast(tuple[Any, ...], value)
        result_tuple = tuple(sanitize_surrogates_deep(item) for item in tuple_value)
        return (
            result_tuple
            if any(a is not b for a, b in zip(result_tuple, tuple_value))
            else cast(Any, value)
        )
    return value


def timestamp() -> str:
    """Current ISO timestamp."""
    return datetime.now().isoformat()


_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*]')


_TRUNCATED_SUFFIX = "\n... (truncated)"


def safe_filename(name: str) -> str:
    """Replace unsafe path characters with underscores."""
    return _UNSAFE_CHARS.sub("_", name).strip()


def truncate_text(text: str, max_chars: int) -> str:
    """Truncate text with a stable suffix."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars] + _TRUNCATED_SUFFIX


def truncate_text_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to a token budget with a stable suffix.

    Uses cl100k_base when ready, which may differ from the model's tokenizer.
    Falls back to a UTF-8 byte budget while loading or if initialization failed.
    """
    if max_tokens <= 0:
        return text
    try:
        enc = token_encoding.get_token_encoding()
        if enc is not None:
            tokens = enc.encode_ordinary(text)
            if len(tokens) <= max_tokens:
                return text
            suffix_tokens = enc.encode_ordinary(_TRUNCATED_SUFFIX)
            body_budget = max_tokens - len(suffix_tokens)
            if body_budget <= 0:
                return enc.decode(tokens[:max_tokens])
            for candidate_budget in range(body_budget, -1, -1):
                result = enc.decode(tokens[:candidate_budget]) + _TRUNCATED_SUFFIX
                if len(enc.encode_ordinary(result)) <= max_tokens:
                    return result
            return enc.decode(tokens[:max_tokens])
    except Exception:
        pass
    if len(text.encode("utf-8")) <= max_tokens:
        return text
    suffix_bytes = len(_TRUNCATED_SUFFIX.encode("utf-8"))
    if max_tokens <= suffix_bytes:
        return _truncate_text_to_utf8_bytes(text, max_tokens)
    body = _truncate_text_to_utf8_bytes(text, max_tokens - suffix_bytes)
    return body + _TRUNCATED_SUFFIX


def _truncate_text_to_utf8_bytes(text: str, max_bytes: int) -> str:
    """Return the longest code-point prefix within a UTF-8 byte budget."""
    if max_bytes <= 0:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def split_message(content: str, max_len: int = 2000) -> list[str]:
    """
    Split content into chunks within max_len, preferring line breaks.

    Args:
        content: The text content to split.
        max_len: Maximum length per chunk (default 2000 for Discord compatibility).

    Returns:
        List of message chunks, each within max_len.
    """
    if not content:
        return []
    # Non-positive max_len cannot advance the cut pointer; return unsplit.
    if max_len <= 0:
        return [content]
    if len(content) <= max_len:
        return [content]
    original_content = content
    chunks: list[str] = []
    while content:
        if len(content) <= max_len:
            if content.strip():
                chunks.append(content)
            break
        cut = content[:max_len]
        # Consume only the newline itself so indentation starts the next chunk.
        newline_pos = cut.rfind("\n")
        if newline_pos >= 0:
            # Exclude both bytes of a CRLF boundary from the emitted chunk.
            line_end = newline_pos
            if line_end > 0 and content[line_end - 1] == "\r":
                line_end -= 1
            chunk = content[:line_end]
            if chunk.strip():
                chunks.append(chunk)
            content = content[newline_pos + 1 :]
            continue

        # Keep the existing word-boundary behavior, but avoid emitting a
        # whitespace-only chunk when an indented line exceeds max_len.
        space_pos = cut.rfind(" ")
        if space_pos > 0 and cut[:space_pos].strip():
            chunks.append(content[:space_pos])
            content = content[space_pos:].lstrip(" \t")
            # A space boundary may sit immediately before a line break. Drop
            # that delimiter too, without stripping the next line's indent.
            if content.startswith("\r\n"):
                content = content[2:]
            elif content.startswith("\n"):
                content = content[1:]
            continue

        # Do not split between the two code points of a CRLF delimiter.
        if cut.endswith("\r") and content[max_len : max_len + 1] == "\n":
            chunk = cut[:-1]
            if chunk.strip():
                chunks.append(chunk)
            content = content[max_len + 1 :]
            continue

        chunk = content[:max_len]
        if chunk.strip():
            chunks.append(chunk)
        content = content[max_len:]
        if not chunk.strip():
            # Keep any remaining indentation so the final non-blank chunk can
            # retain as much of it as the channel limit permits.
            continue
        # A delimiter can sit immediately after the hard-break boundary. Keep
        # ordinary space trimming, but consume only the newline so indentation
        # on the following line is preserved.
        content = content.lstrip(" \t")
        if content.startswith("\r\n"):
            content = content[2:]
        elif content.startswith("\n"):
            content = content[1:]
    # Preserve the historical non-empty-input contract for callers that take
    # the first chunk directly. This fallback is only reachable for content
    # made entirely of whitespace.
    return chunks or [original_content[:max_len]]
