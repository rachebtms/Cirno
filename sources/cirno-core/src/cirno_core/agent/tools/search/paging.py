"""Output-size and offset paging shared by path and content search."""

from typing import TypeVar

T = TypeVar("T")


def _paginate(items: list[T], limit: int | None, offset: int) -> tuple[list[T], bool]:
    if limit is None:
        return items[offset:], False
    sliced = items[offset : offset + limit]
    truncated = len(items) > offset + limit
    return sliced, truncated


def text_page(
    items: list[str],
    limit: int | None,
    offset: int,
    max_chars: int,
) -> tuple[list[str], bool]:
    page, truncated = _paginate(items, limit, offset)
    size = 0
    for index, item in enumerate(page):
        size += len(item) + (1 if index else 0)
        if size > max_chars:
            if index == 0:
                raise ValueError("Search entry exceeds output budget; narrow the search path")
            return page[:index], True
    return page, truncated


def pagination_note(limit: int | None, offset: int, truncated: bool) -> str | None:
    if truncated:
        if limit is None:
            return f"(pagination: offset={offset})"
        return f"(pagination: limit={limit}, offset={offset})"
    if offset > 0:
        return f"(pagination: offset={offset})"
    return None
