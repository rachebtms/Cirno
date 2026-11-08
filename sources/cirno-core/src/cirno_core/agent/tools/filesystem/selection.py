"""Count matches while retaining only the requested location and error previews."""

from collections.abc import Iterable
from dataclasses import dataclass
from threading import Event

from cirno_core.agent.tools.filesystem.matching import _match_covers_line, _MatchSpan


@dataclass(frozen=True)
class MatchSelection:
    count: int
    preview_lines: tuple[int, ...]
    chosen: tuple[_MatchSpan, ...]


def select_matches(
    matches: Iterable[_MatchSpan],
    *,
    occurrence: int | None,
    line_hint: int | None,
    cancelled: Event,
) -> MatchSelection:
    count = 0
    preview: list[int] = []
    chosen: list[_MatchSpan] = []
    for count, match in enumerate(matches, 1):
        if count % 1024 == 0 and cancelled.is_set():
            raise InterruptedError("File edit preparation cancelled")
        if count <= 3:
            preview.append(match.line)
        if line_hint is not None:
            if len(chosen) < 2 and _match_covers_line(match, line_hint):
                chosen.append(match)
        elif count == (occurrence or 1):
            chosen.append(match)
    return MatchSelection(count, tuple(preview), tuple(chosen))
