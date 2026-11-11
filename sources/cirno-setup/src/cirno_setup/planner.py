"""Resolve each dependency once and reject cycles before making any changes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cirno_setup.recipe import Recipe
from cirno_setup.registry import catalogue, normalize, resolve

if TYPE_CHECKING:
    from cirno_setup.context import Context


@dataclass(frozen=True)
class Step:
    name: str
    recipe: Recipe


def plan(context: Context, selectors: list[str], registered: dict[str, Recipe] | None = None) -> list[Step]:
    entries = catalogue() if registered is None else registered
    done: set[str] = set()
    active: list[str] = []
    result: list[Step] = []

    def visit(selector: str) -> None:
        name = normalize(selector)
        if name in active:
            raise ValueError("Setup dependency cycle: " + " -> ".join([*active, name]))
        if name in done:
            return
        recipe = resolve(name, entries)
        active.append(name)
        for dependency in recipe.depends(context):
            visit(dependency)
        active.pop()
        done.add(name)
        if recipe.provider != "group":
            result.append(Step(name, recipe))

    for selector in selectors:
        visit(selector)
    return result
