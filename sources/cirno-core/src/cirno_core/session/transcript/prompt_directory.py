"""Bounded pages and text search over the canonical prompt projection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, TypedDict

from cirno_core.session.display_history import HistoryReader

from .inputs import session_backfill_turns
from .prompts import PromptSummary, prompt_view_snapshot

PROMPT_PAGE_SIZE = 64
MAX_PROMPT_PAGE_SIZE = 256
_MODEL_COMMAND = re.compile(r"^/model(?:@[A-Za-z0-9_]+)?(?:\s|$)", re.IGNORECASE)


class DirectoryPrompt(PromptSummary):
    index: int


class PromptPage(TypedDict):
    prompts: list[DirectoryPrompt]
    offset: int
    total: int
    count: int
    revision: str | None


@dataclass(frozen=True)
class PromptPageRequest:
    offset: int | None = None
    limit: int = PROMPT_PAGE_SIZE
    query: str = ""

    def __post_init__(self) -> None:
        if self.offset is not None and (self.offset < 0 or self.offset > 2**53 - 1):
            raise ValueError("offset must be a non-negative safe integer")
        if not 1 <= self.limit <= MAX_PROMPT_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_PROMPT_PAGE_SIZE}")


def prompt_directory_page(
    session_key: str,
    *,
    history: HistoryReader,
    request: PromptPageRequest = PromptPageRequest(),
    session_messages_loader: Callable[[], list[dict[str, Any]] | None] | None = None,
    session_version_loader: Callable[[], tuple[str, int] | None] | None = None,
) -> PromptPage:
    """Omitted offsets select the latest page; search keeps original prompt positions."""
    view, revision = prompt_view_snapshot(
        session_key,
        history=history,
        session_turns_loader=lambda: session_backfill_turns(
            session_key,
            (session_messages_loader() if session_messages_loader else None) or [],
        ),
        session_version_loader=session_version_loader,
    )
    needle = request.query.strip().casefold()
    matches: list[tuple[int, PromptSummary]] = []
    count = 0
    for prompt in view.prompts:
        if prompt["turnId"].startswith("webui-system:") or _MODEL_COMMAND.match(
            prompt["preview"].strip()
        ):
            continue
        index = count
        count += 1
        if not needle or needle in prompt["preview"].casefold():
            matches.append((index, prompt))
    start = (
        max(0, len(matches) - request.limit)
        if request.offset is None
        else min(request.offset, len(matches))
    )
    return {
        "prompts": [
            DirectoryPrompt(**prompt, index=index)
            for index, prompt in matches[start : start + request.limit]
        ],
        "offset": start,
        "total": len(matches),
        "count": count,
        "revision": revision,
    }
