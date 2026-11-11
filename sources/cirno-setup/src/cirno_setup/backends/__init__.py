"""Installation providers implement the same verify/install contract."""

from importlib import import_module
from typing import Protocol, cast

from cirno_setup.context import Context
from cirno_setup.recipe import Recipe, Verification

_PROVIDERS = {"apt", "pip", "npm", "brew", "archive", "homebrew", "browser", "embedding", "extra", "nvm", "node"}


class Backend(Protocol):
    def verify(self, context: Context, recipe: Recipe) -> Verification: ...
    def install(self, context: Context, recipe: Recipe) -> None: ...


def backend(name: str) -> Backend:
    if name not in _PROVIDERS:
        raise ValueError(f"Unknown setup provider: {name}")
    return cast(Backend, import_module(f"cirno_setup.backends.{name}"))
