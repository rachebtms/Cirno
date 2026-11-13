"""Telegram command aliases and presentation."""

import re

from cirno_core.command.builtin.catalog import BUILTIN_COMMAND_SPECS

TELEGRAM_MENU_SPECS = tuple(
    spec for spec in BUILTIN_COMMAND_SPECS
    if not spec.hidden and spec.command not in {"/temporary", "/ptc"}
)
_BUS_NAMES = {
    name[1:] for spec in BUILTIN_COMMAND_SPECS
    if spec.command not in {"/temporary", "/ptc", "/help"}
    for name in (spec.command, *spec.aliases)
}
TELEGRAM_BUS_SLASH_COMMAND_RE = re.compile(
    r"^/(?:" + "|".join(re.escape(name.replace("-", "_")) for name in sorted(_BUS_NAMES))
    + r")(?:@\w+)?(?:\s+[\s\S]*)?$", re.IGNORECASE,
)
TELEGRAM_HYPHENATED_COMMAND_RE = re.compile(
    r"^/(?:" + "|".join(re.escape(name) for name in sorted(_BUS_NAMES) if "-" in name)
    + r")(?:@\w+)?(?:\s+[\s\S]*)?$", re.IGNORECASE,
)

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
