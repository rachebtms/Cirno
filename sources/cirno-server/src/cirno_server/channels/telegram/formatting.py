"""Telegram Markdown rendering and message chunk boundaries."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from html.parser import HTMLParser

from cirno_server.channels.telegram.limits import TELEGRAM_MAX_MESSAGE_LEN

_FENCE_OPEN_RE = re.compile(r'^[ \t]*(`{3,}|~{3,})(.*)$')
_INLINE_FENCE_RE = re.compile(r'```(?:[^\n]*\n)?([\s\S]*?)```')


def _opening_code_fence(line: str) -> str | None:
    match = _FENCE_OPEN_RE.match(line)
    if match and not (match.group(1)[0] == '`' and '`' in match.group(2)):
        return match.group(1)
    return None


def _closes_code_fence(line: str, fence: str) -> bool:
    closing = line.strip()
    return len(closing) >= len(fence) and closing == fence[0] * len(closing)


@dataclass(frozen=True)
class TelegramMarkdownFragment:
    markdown: str
    source: str
    line_continuation: bool
    remainder: str
    remainder_line_continuation: bool


def iter_telegram_markdown_fragments(
    content: str, max_len: int, *, line_continuation: bool = False,
) -> Iterator[TelegramMarkdownFragment]:
    """Yield bounded fragments with the exact resume state for each commit."""
    if max_len <= 0:
        raise ValueError("Telegram chunk length must be positive")
    if not content:
        return
    content = content.lstrip()
    if not content:
        return

    def after_cut(pos: int) -> tuple[str, bool]:
        rest = content[pos:]
        trimmed = rest.lstrip()
        removed = rest[:len(rest) - len(trimmed)]
        midline = content[pos - 1:pos] != "\n" and "\n" not in removed
        return trimmed, midline

    def fence_line(fence_pos: int) -> str:
        line_end = content.find("\n", fence_pos)
        if line_end < 0:
            return content[fence_pos:]
        return content[fence_pos:line_end]

    def split_inside_fenced_code_block(pos: int) -> tuple[int, str, str] | None:
        fence = None
        opening = -1
        inline = False
        offset = 0
        for line in content[:pos].split("\n"):
            if fence is not None and not inline:
                if _closes_code_fence(line, fence):
                    fence = None
            else:
                marker = (
                    _opening_code_fence(line)
                    if fence is None and not (offset == 0 and line_continuation) else None
                )
                if marker is not None:
                    fence = marker
                    opening = offset
                    inline = False
                else:
                    # Keep the legacy renderer's inline triple-backtick blocks.
                    for match in re.finditer("```", line):
                        if fence is None:
                            fence = "```"
                            opening = offset + match.start()
                            inline = True
                        else:
                            fence = None
                            inline = False
            offset += len(line) + 1
        return (opening, fence_line(opening), fence) if fence is not None else None

    while content:
        if len(content) <= max_len:
            yield TelegramMarkdownFragment(content, content, line_continuation, "", False)
            break

        cut = content[:max_len]
        pos = cut.rfind("\n")
        if pos <= 0:
            pos = cut.rfind(" ")
        if pos <= 0:
            pos = max_len

        active_fence = split_inside_fenced_code_block(pos)
        if active_fence is not None:
            opening, fence, marker = active_fence
            if opening > 0:
                pos = opening
            else:
                closing = "\n" + marker
                min_code_pos = len(fence)
                if content.startswith(fence + "\n"):
                    min_code_pos += 1
                # When the only break in range is the opening fence newline,
                # cutting there re-emits the same fence and never advances.
                if pos < min_code_pos:
                    if min_code_pos + len(closing) >= max_len:
                        rest, midline = after_cut(max_len)
                        yield TelegramMarkdownFragment(content[:max_len], content, line_continuation, rest, midline)
                        content, line_continuation = rest, midline
                        continue
                    budget = max_len - len(closing)
                    recut = content[:budget]
                    adjusted = recut.rfind("\n", min_code_pos)
                    if adjusted < min_code_pos:
                        adjusted = recut.rfind(" ", min_code_pos)
                    pos = adjusted if adjusted > min_code_pos else budget
                elif pos + len(closing) > max_len:
                    budget = max_len - len(closing)
                    if budget <= min_code_pos:
                        rest, midline = after_cut(max_len)
                        yield TelegramMarkdownFragment(content[:max_len], content, line_continuation, rest, midline)
                        content, line_continuation = rest, midline
                        continue
                    recut = content[:budget]
                    adjusted = recut.rfind("\n", min_code_pos)
                    if adjusted < min_code_pos:
                        adjusted = recut.rfind(" ", min_code_pos)
                    pos = adjusted if adjusted > min_code_pos else budget
                if pos <= min_code_pos:
                    rest, midline = after_cut(max_len)
                    yield TelegramMarkdownFragment(content[:max_len], content, line_continuation, rest, midline)
                    content, line_continuation = rest, midline
                    continue
                remainder = content[pos:]
                if remainder.startswith("\n"):
                    remainder = remainder[1:]
                rest = f"{fence}\n{remainder}"
                yield TelegramMarkdownFragment(content[:pos] + closing, content, line_continuation, rest, False)
                content, line_continuation = rest, False
                continue

        rest, midline = after_cut(pos)
        yield TelegramMarkdownFragment(content[:pos], content, line_continuation, rest, midline)
        content, line_continuation = rest, midline


def split_telegram_markdown(content: str, max_len: int) -> list[str]:
    """Compatibility projection for callers that only need the raw fragments."""
    return [chunk.markdown for chunk in iter_telegram_markdown_fragments(content, max_len)]


def _escape_telegram_html(text: str) -> str:
    """Escape text for Telegram HTML parse mode."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def tool_hint_to_telegram_blockquote(text: str) -> str:
    """Render tool hints as an expandable blockquote (collapsed by default)."""
    return f"<blockquote expandable>{_escape_telegram_html(text)}</blockquote>" if text else ""


def rich_markdown_continuation(content: str) -> str:
    """Escape only a newly exposed block marker; retain native rich Markdown.

    GFM character references display the literal symbol without defining a
    structural marker. Keep the rest unchanged for native media/math/formatting.
    """
    first = content.partition("\n")[0]
    block_start = re.match(
        r"^[ \t]{0,3}(?:#{1,6}(?:[ \t]|$)|>|[-+*](?:[ \t]|$)|[0-9]{1,9}[.)](?:[ \t]|$)|\|)", first,
    )
    thematic_break = re.fullmatch(r"[ \t]*([-*_])(?:[ \t]*\1){2,}[ \t]*", first)
    if not (block_start or thematic_break or _opening_code_fence(first)):
        return content
    start = len(first) - len(first.lstrip(" \t"))
    return content[:start] + f"&#{ord(content[start])};" + content[start + 1:]


def _strip_md(s: str) -> str:
    """Strip markdown inline formatting from text."""
    s = re.sub(r'\*\*(.+?)\*\*', r'\1', s)
    s = re.sub(r'__(.+?)__', r'\1', s)
    s = re.sub(r'~~(.+?)~~', r'\1', s)
    s = re.sub(r'`([^`]+)`', r'\1', s)
    return s.strip()


def _replace_fenced_code(
    text: str, replace: Callable[[str], str], *, line_continuation: bool = False,
) -> str:
    """Replace fenced code blocks with ``replace(code)``.

    A block opens on a ``` or ~~~ line and closes on a line holding only a run
    of the same character that is at least as long, so tilde fences work and a
    ```` fence can show a ``` example. What remains (one-line ```code``` and
    unclosed fences) keeps the previous regex handling.
    """
    lines = text.split('\n')
    out: list[str] = []
    i = 0
    while i < len(lines):
        fence = _opening_code_fence(lines[i]) if i != 0 or not line_continuation else None
        if fence is not None:
            for j in range(i + 1, len(lines)):
                if _closes_code_fence(lines[j], fence):
                    out.append(replace(''.join(line + '\n' for line in lines[i + 1:j])))
                    i = j + 1
                    break
            else:
                out.append(lines[i])
                i += 1
            continue
        out.append(lines[i])
        i += 1
    text = '\n'.join(out)
    return _INLINE_FENCE_RE.sub(lambda m: replace(m.group(1)), text)


def _block_sub(pattern: str, replacement: str, text: str, continuation: bool) -> str:
    if continuation:
        first, newline, rest = text.partition("\n")
        return first + newline + re.sub(pattern, replacement, rest, flags=re.MULTILINE)
    return re.sub(pattern, replacement, text, flags=re.MULTILINE)


def strip_md_block(text: str, *, line_continuation: bool = False) -> str:
    """Strip block-level and inline markdown for readable plain-text preview.

    Used during streaming mid-edits so users see clean text instead of raw
    markdown syntax while the response is still being generated.
    """
    # Code blocks -> just the code
    text = _replace_fenced_code(text, lambda code: code, line_continuation=line_continuation)
    # Headers -> plain text
    text = _block_sub(r'^#{1,6}\s+(.+)$', r'\1', text, line_continuation)
    # Blockquotes
    text = _block_sub(r'^>\s*(.*)$', r'\1', text, line_continuation)
    # Bold / italic / strikethrough
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])', r'\1', text)
    text = re.sub(r'~~(.+?)~~', r'\1', text)
    # Inline code
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Links [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Bullet lists
    text = _block_sub(r'^[-*]\s+', '• ', text, line_continuation)
    # Numbered lists (normalize spacing)
    text = _block_sub(r'^(\d+)\.\s+', r'\1. ', text, line_continuation)
    return text


def _render_table_box(table_lines: list[str]) -> str:
    """Convert markdown pipe-table to compact aligned text for <pre> display."""

    def dw(s: str) -> int:
        return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in s)

    def cells(line: str) -> list[str]:
        text = line.strip()
        if text.startswith('|'):
            text = text[1:]
        if text.endswith('|'):
            text = text[:-1]
        return [_strip_md(cell) for cell in text.split('|')]

    if len(table_lines) < 2:
        return '\n'.join(table_lines)
    header, separator = cells(table_lines[0]), cells(table_lines[1])
    if len(header) != len(separator) or not all(re.fullmatch(r':?-+:?', cell) for cell in separator):
        return '\n'.join(table_lines)
    rows = [header, *[cells(line) for line in table_lines[2:]]]

    ncols = max(len(r) for r in rows)
    for r in rows:
        r.extend([''] * (ncols - len(r)))
    widths = [max(dw(r[c]) for r in rows) for c in range(ncols)]

    def dr(cells: list[str]) -> str:
        return '  '.join(f'{c}{" " * (w - dw(c))}' for c, w in zip(cells, widths))

    out = [dr(rows[0])]
    out.append('  '.join('─' * w for w in widths))
    for row in rows[1:]:
        out.append(dr(row))
    return '\n'.join(out)


def markdown_to_telegram_html(text: str, *, line_continuation: bool = False) -> str:
    """
    Convert markdown to Telegram-safe HTML.
    """
    if not text:
        return ""

    # 1. Extract and protect code blocks (preserve content from other processing)
    code_blocks: list[str] = []
    def save_code_block(code: str) -> str:
        code_blocks.append(code)
        return f"\x00CB{len(code_blocks) - 1}\x00"

    text = _replace_fenced_code(text, save_code_block, line_continuation=line_continuation)

    # 1.5. Convert markdown tables to box-drawing (reuse code_block placeholders)
    lines = text.split('\n')
    rebuilt: list[str] = []
    li = 0
    while li < len(lines):
        if not (li == 0 and line_continuation) and re.match(r'^\s*\|.+\|', lines[li]):
            tbl: list[str] = []
            while li < len(lines) and re.match(r'^\s*\|.+\|', lines[li]):
                tbl.append(lines[li])
                li += 1
            box = _render_table_box(tbl)
            if box != '\n'.join(tbl):
                code_blocks.append(box)
                rebuilt.append(f"\x00CB{len(code_blocks) - 1}\x00")
            else:
                rebuilt.extend(tbl)
        else:
            rebuilt.append(lines[li])
            li += 1
    text = '\n'.join(rebuilt)

    # 2. Extract and protect inline code
    inline_codes: list[str] = []
    def save_inline_code(m: re.Match[str]) -> str:
        inline_codes.append(m.group(1))
        return f"\x00IC{len(inline_codes) - 1}\x00"

    text = re.sub(r'`([^`]+)`', save_inline_code, text)

    # 3. Headers # Title -> <b>Title</b> (preserve visual hierarchy)
    text = _block_sub(r'^#{1,6}\s+(.+)$', r'⟪B⟫\1⟪/B⟫', text, line_continuation)

    # 4. Blockquotes > text -> just the text (before HTML escaping)
    text = _block_sub(r'^>\s*(.*)$', r'\1', text, line_continuation)

    # 5. Escape HTML special characters
    text = _escape_telegram_html(text)

    # 6. Links [text](url) - must be before bold/italic to handle nested cases.
    # Park the URL in a placeholder so later inline-formatting passes cannot
    # rewrite it (e.g. ``__init__.py`` must not become ``<b>init</b>.py``).
    link_urls: list[str] = []
    def save_link(m: re.Match[str]) -> str:
        link_urls.append(m.group(2).replace('"', "&quot;"))
        return f'<a href="\x00LK{len(link_urls) - 1}\x00">{m.group(1)}</a>'

    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', save_link, text)

    # 7. Bold **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)

    # 8. Italic _text_ (avoid matching inside words like some_var_name)
    text = re.sub(r'(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])', r'<i>\1</i>', text)

    # 9. Strikethrough ~~text~~
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)

    # 10. Bullet lists - item -> • item
    text = _block_sub(r'^[-*]\s+', '• ', text, line_continuation)

    # 10.5. Numbered lists  1. item -> 1. item (keep number, normalize indent)
    text = _block_sub(r'^(\d+)\.\s+', r'\1. ', text, line_continuation)

    # 10.6. Restore link URLs protected in step 6
    for i, url in enumerate(link_urls):
        text = text.replace(f"\x00LK{i}\x00", url)

    # 11. Restore inline code with HTML tags
    for i, code in enumerate(inline_codes):
        # Escape HTML in code content
        escaped = _escape_telegram_html(code)
        text = text.replace(f"\x00IC{i}\x00", f"<code>{escaped}</code>")

    # 12. Restore code blocks with HTML tags
    for i, code in enumerate(code_blocks):
        # Escape HTML in code content
        escaped = _escape_telegram_html(code)
        text = text.replace(f"\x00CB{i}\x00", f"<pre><code>{escaped}</code></pre>")

    # 13. Restore header bold markers inserted in step 3 before HTML escaping.
    text = text.replace('⟪B⟫', '<b>').replace('⟪/B⟫', '</b>')

    return text


class _TelegramHTMLTextLength(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.length = 0

    def handle_data(self, data: str) -> None:
        self.length += len(data)


def telegram_html_text_length(html: str) -> int:
    """Bot API limits apply after parsing entities, excluding tags/attributes."""
    parser = _TelegramHTMLTextLength()
    parser.feed(html)
    parser.close()
    return parser.length


def iter_telegram_markdown_html_fragments(
    content: str, max_html_len: int, *, render: Callable[[str], str] | None = None,
    line_continuation: bool = False,
) -> Iterator[tuple[TelegramMarkdownFragment, str]]:
    """Return raw/HTML pairs bounded by text length after entity parsing.

    ``max_html_len`` retains its existing spelling; it limits displayed text,
    not HTML tag, attribute or escaped-entity source characters.
    """
    if max_html_len <= 0:
        raise ValueError("Telegram displayed-text limit must be positive")
    while content:
        raw_limit = TELEGRAM_MAX_MESSAGE_LEN
        while True:
            chunk = next(iter_telegram_markdown_fragments(
                content, raw_limit, line_continuation=line_continuation,
            ), None)
            if chunk is None:
                return
            html = render(chunk.markdown) if render is not None else markdown_to_telegram_html(
                chunk.markdown, line_continuation=chunk.line_continuation,
            )
            text_len = telegram_html_text_length(html)
            if text_len <= max_html_len:
                break
            # Re-cut the original remainder, retaining its logical-line context.
            # Re-splitting an already balanced fragment would insert new fences.
            raw_limit = min(raw_limit - 1, len(chunk.markdown) - 1,
                            max(1, int(len(chunk.markdown) * max_html_len / text_len) - 8))
            if raw_limit <= 0:
                raise ValueError("A rendered Telegram HTML token exceeds the message limit")
        yield chunk, html
        content, line_continuation = chunk.remainder, chunk.remainder_line_continuation


def split_telegram_markdown_html_chunks(
    content: str, max_html_len: int, *, render: Callable[[str], str] | None = None,
) -> list[tuple[str, str]]:
    return [(chunk.markdown, html) for chunk, html in iter_telegram_markdown_html_fragments(
        content, max_html_len, render=render,
    )]


def split_telegram_markdown_html(content: str, max_html_len: int) -> list[str]:
    """Split raw Telegram Markdown and return HTML chunks within Telegram's limit."""
    return [html for _, html in split_telegram_markdown_html_chunks(content, max_html_len)]
