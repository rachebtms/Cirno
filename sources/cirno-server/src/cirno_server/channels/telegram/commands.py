"""Telegram command aliases and presentation."""

import re

_TELEGRAM_COMMAND_ALIASES = {
    "/dream_log": "/dream-log",
    "/dream_restore": "/dream-restore",
    "/dream_prompt": "/dream-prompt",
}
_TELEGRAM_DISPLAY_COMMAND_RE = re.compile(
    r"(?<![\w/.-])/(?:dream-log|dream-restore|dream-prompt)(?![\w/.-])"
)


def telegram_command_text(text: str) -> str:
    """Render command references for Telegram without changing fenced code or diffs."""
    display_names = {value: key for key, value in _TELEGRAM_COMMAND_ALIASES.items()}
    lines: list[str] = []
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
        elif stripped.startswith(("```", "~~~")):
            fence = stripped[:3]
        else:
            line = _TELEGRAM_DISPLAY_COMMAND_RE.sub(lambda match: display_names[match[0]], line)
            # Inline code is not tappable as a Telegram command.
            line = re.sub(
                r"`(/(?:dream_log|dream_restore|dream_prompt)(?: [^`\n]*)?)`",
                r"\1",
                line,
            )
        lines.append(line)
    return "".join(lines)
