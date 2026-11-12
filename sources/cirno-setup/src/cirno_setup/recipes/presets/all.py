"""Complete built-in catalogue, primarily for CI installation coverage."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cirno_setup.recipe import Recipe

if TYPE_CHECKING:
    from cirno_setup.context import Context


class AllRecipes(Recipe):
    def depends(self, context: Context) -> tuple[str, ...]:
        from cirno_setup.registry import catalogue

        return tuple(name for name in catalogue() if name != "presets.all")


recipe = AllRecipes(description="Every built-in setup component, for comprehensive verification")
