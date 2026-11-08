"""Evidence writer used before releasing archived runtime messages."""

from collections.abc import Callable, Iterable, Mapping
from typing import Any, TypeAlias

ArchiveWriter: TypeAlias = Callable[[Iterable[dict[str, Any]], str | None], Mapping[str, Any]]
