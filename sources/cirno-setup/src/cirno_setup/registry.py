"""Namespaced recipes with generic package backends and deterministic discovery."""

from __future__ import annotations

import importlib
import pkgutil
import re
from functools import lru_cache

from packaging.requirements import Requirement

from cirno_setup import recipes
from cirno_setup.apt import APT_PACKAGE
from cirno_setup.recipe import Recipe

BREW_PACKAGE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9@+_.-]*(?:/[a-zA-Z0-9@+_.-]+){0,2}")
NPM_PACKAGE = re.compile(r"(?:@[a-z0-9_.-]+/)?[a-z0-9][a-z0-9_.-]*(?:@[0-9]+(?:\.[0-9]+){2}(?:-[a-zA-Z0-9.-]+)?)?")
ALIASES = {"rachebtms": "presets.rachebtms"}


@lru_cache(maxsize=1)
def catalogue() -> dict[str, Recipe]:
    result: dict[str, Recipe] = {}
    prefix = recipes.__name__ + "."
    for module in pkgutil.walk_packages(recipes.__path__, prefix):
        if not module.ispkg:
            result[module.name.removeprefix(prefix)] = importlib.import_module(module.name).recipe
    return dict(sorted(result.items()))


def normalize(selector: str) -> str:
    name = selector.removeprefix("+")
    if not name or name.startswith(("-", "+")) or any(char.isspace() for char in name):
        raise ValueError(f"Invalid setup selector: {selector!r}")
    return ALIASES.get(name, name)


def resolve(selector: str, registered: dict[str, Recipe] | None = None) -> Recipe:
    name = normalize(selector)
    entries = catalogue() if registered is None else registered
    if name in entries:
        return entries[name]
    namespace, _, package = name.partition(".")
    if namespace == "pip":
        requirement = Requirement(package)
        if requirement.url is None and requirement.marker is None:
            return Recipe("pip", (package,), description=package)
    if namespace == "apt" and APT_PACKAGE.fullmatch(package):
        return Recipe("apt", (package,), description=package)
    if namespace == "brew" and BREW_PACKAGE.fullmatch(package):
        return Recipe("brew", (package,), ("tools.homebrew",), description=package)
    if namespace == "npm" and NPM_PACKAGE.fullmatch(package):
        return Recipe("npm", (package,), ("tools.node",), description=package)
    raise ValueError(f"Unknown setup component: {name}")
