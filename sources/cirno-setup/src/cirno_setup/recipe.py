"""The common contract used by package, tool and preset modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cirno_setup.context import Context


@dataclass(frozen=True)
class Verification:
    ready: bool
    reason: str = ""


@dataclass(frozen=True)
class Recipe:
    provider: str = "group"
    packages: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    imports: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    target: str = "tools"
    description: str = ""
    revision: str = "1"

    def depends(self, context: Context) -> tuple[str, ...]:
        return self.dependencies

    def verify(self, context: Context) -> Verification:
        from cirno_setup.backends import backend

        return backend(self.provider).verify(context, self)

    def install(self, context: Context) -> None:
        from cirno_setup.backends import backend

        backend(self.provider).install(context, self)
