"""Telegram Markdown rendering and message chunk boundaries."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

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


def split_telegram_markdown(content: str, max_len: int) -> list[str]:
    """Split raw Telegram Markdown without leaving fenced code blocks unbalanced."""
    if not content:
        return []
    content = content.lstrip()
    if not content:
        return []
    if len(content) <= max_len:
        return [content]

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
                marker = _opening_code_fence(line) if fence is None else None
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

    chunks: list[str] = []
    while content:
        if len(content) <= max_len:
            chunks.append(content)
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
                        chunks.append(content[:max_len])
                        content = content[max_len:].lstrip()
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
                        chunks.append(content[:max_len])
                        content = content[max_len:].lstrip()
                        continue
                    recut = content[:budget]
                    adjusted = recut.rfind("\n", min_code_pos)
                    if adjusted < min_code_pos:
                        adjusted = recut.rfind(" ", min_code_pos)
                    pos = adjusted if adjusted > min_code_pos else budget
                if pos <= min_code_pos:
                    chunks.append(content[:max_len])
                    content = content[max_len:].lstrip()
                    continue
                chunks.append(content[:pos] + closing)
                remainder = content[pos:]
                if remainder.startswith("\n"):
                    remainder = remainder[1:]
                content = f"{fence}\n{remainder}"
                continue

        chunks.append(content[:pos])
        content = content[pos:].lstrip()
    return chunks


def _escape_telegram_html(text: str) -> str:
    """Escape text for Telegram HTML parse mode."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def tool_hint_to_telegram_blockquote(text: str) -> str:
    """Render tool hints as an expandable blockquote (collapsed by default)."""
    return f"<blockquote expandable>{_escape_telegram_html(text)}</blockquote>" if text else ""


def _strip_md(s: str) -> str:
    """Strip markdown inline formatting from text."""
    s = re.sub(r'\*\*(.+?)\*\*', r'\1', s)
    s = re.sub(r'__(.+?)__', r'\1', s)
    s = re.sub(r'~~(.+?)~~', r'\1', s)
    s = re.sub(r'`([^`]+)`', r'\1', s)
    return s.strip()


def _replace_fenced_code(text: str, replace: Callable[[str], str]) -> str:
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
        fence = _opening_code_fence(lines[i])
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


def strip_md_block(text: str) -> str:
    """Strip block-level and inline markdown for readable plain-text preview.

    Used during streaming mid-edits so users see clean text instead of raw
    markdown syntax while the response is still being generated.
    """
    # Code blocks -> just the code
    text = _replace_fenced_code(text, lambda code: code)
    # Headers -> plain text
    text = re.sub(r'^#{1,6}\s+(.+)$', r'\1', text, flags=re.MULTILINE)
    # Blockquotes
    text = re.sub(r'^>\s*(.*)$', r'\1', text, flags=re.MULTILINE)
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
    text = re.sub(r'^[-*]\s+', '• ', text, flags=re.MULTILINE)
    # Numbered lists (normalize spacing)
    text = re.sub(r'^(\d+)\.\s+', r'\1. ', text, flags=re.MULTILINE)
    return text


def _render_table_box(table_lines: list[str]) -> str:
    """Convert markdown pipe-table to compact aligned text for <pre> display."""

    def dw(s: str) -> int:
        return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in s)

    rows: list[list[str]] = []
    has_sep = False
    for line in table_lines:
        cells = [_strip_md(c) for c in line.strip().strip('|').split('|')]
        if all(re.match(r'^:?-+:?$', c) for c in cells if c):
            has_sep = True
            continue
        rows.append(cells)
    if not rows or not has_sep:
        return '\n'.join(table_lines)

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


def markdown_to_telegram_html(text: str) -> str:
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

    text = _replace_fenced_code(text, save_code_block)

    # 1.5. Convert markdown tables to box-drawing (reuse code_block placeholders)
    lines = text.split('\n')
    rebuilt: list[str] = []
    li = 0
    while li < len(lines):
        if re.match(r'^\s*\|.+\|', lines[li]):
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
    text = re.sub(r'^#{1,6}\s+(.+)$', r'⟪B⟫\1⟪/B⟫', text, flags=re.MULTILINE)

    # 4. Blockquotes > text -> just the text (before HTML escaping)
    text = re.sub(r'^>\s*(.*)$', r'\1', text, flags=re.MULTILINE)

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
    text = re.sub(r'^[-*]\s+', '• ', text, flags=re.MULTILINE)

    # 10.5. Numbered lists  1. item -> 1. item (keep number, normalize indent)
    text = re.sub(r'^(\d+)\.\s+', r'\1. ', text, flags=re.MULTILINE)

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


def split_telegram_markdown_html_chunks(
    content: str, max_html_len: int,
) -> list[tuple[str, str]]:
    """Return raw Markdown and rendered HTML chunk pairs within Telegram's limit."""
    chunks: list[tuple[str, str]] = []
    pending = split_telegram_markdown(content, TELEGRAM_MAX_MESSAGE_LEN)
    while pending:
        chunk = pending.pop(0)
        html = markdown_to_telegram_html(chunk)
        if len(html) <= max_html_len:
            chunks.append((chunk, html))
            continue

        # Markdown can expand when rendered as HTML (tags/entities). Re-split
        # the raw markdown with a smaller budget instead of slicing HTML tags.
        next_limit = max(1, int(len(chunk) * max_html_len / len(html)) - 8)
        next_limit = min(next_limit, len(chunk) - 1)
        if next_limit <= 0:
            raise ValueError("A rendered Telegram HTML token exceeds the message limit")
        parts = split_telegram_markdown(chunk, next_limit)
        if len(parts) == 1 and parts[0] == chunk:
            raise ValueError("Unable to split Telegram Markdown within the HTML limit")
        pending = parts + pending
    return chunks


def split_telegram_markdown_html(content: str, max_html_len: int) -> list[str]:
    """Split raw Telegram Markdown and return HTML chunks within Telegram's limit."""
    return [html for _, html in split_telegram_markdown_html_chunks(content, max_html_len)]
