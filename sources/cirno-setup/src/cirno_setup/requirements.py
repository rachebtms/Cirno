"""Verify distribution versions and requested extras using one shared algorithm."""

from importlib.metadata import PackageNotFoundError, distribution
from typing import Any, Callable, cast

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def requirement_installed(raw: str, extra: str = "", *, lookup: Callable[[str], Any] = distribution) -> bool:
    return _installed(Requirement(raw), extra, set(), lookup)


def _installed(req: Requirement, extra: str, seen: set[tuple[str, tuple[str, ...]]], lookup: Callable[[str], Any]) -> bool:
    if req.marker and not req.marker.evaluate({"extra": extra}):
        return True
    key = (canonicalize_name(req.name), tuple(sorted(req.extras)))
    if key in seen:
        return True
    seen.add(key)
    try:
        dist = lookup(req.name)
    except PackageNotFoundError:
        return False
    if req.specifier and not req.specifier.contains(dist.version, prereleases=True):
        return False
    for requested in req.extras:
        provided = {canonicalize_name(value) for value in cast(list[str], dist.metadata.get_all("Provides-Extra") or [])}
        if provided and canonicalize_name(requested) not in provided:
            return False
        matched = False
        for raw in cast(list[str], dist.requires or []):
            dependency = Requirement(raw)
            if dependency.marker and not dependency.marker.evaluate({"extra": requested}):
                continue
            matched = True
            if not _installed(dependency, requested, seen, lookup):
                return False
        if not matched and not provided:
            return False
    return True
