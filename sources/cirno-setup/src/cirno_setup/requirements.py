"""Verify distribution versions and requested extras using one shared algorithm."""

from importlib.metadata import PackageNotFoundError, distribution
from typing import Any, Callable, cast

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version


def requirement_installed(raw: str, extra: str = "", *, lookup: Callable[[str], Any] = distribution) -> bool:
    return _installed(Requirement(raw), extra, set(), lookup)


def _installed(req: Requirement, extra: str, seen: set[tuple[str, tuple[str, ...]]], lookup: Callable[[str], Any]) -> bool:
    if req.marker and not req.marker.evaluate({"extra": extra}):
        return True
    key = (canonicalize_name(req.name), tuple(sorted(req.extras)))
    try:
        dist = lookup(req.name)
    except PackageNotFoundError:
        return False
    try:
        version = Version(dist.version)
    except (InvalidVersion, TypeError):
        return False
    if req.specifier and not req.specifier.contains(version, prereleases=True):
        return False
    # Repeated paths may constrain the same package differently. Check each
    # requirement before suppressing recursive expansion of its extras.
    if key in seen:
        return True
    seen.add(key)
    # Plain requirements need their base dependency closure too. Otherwise a
    # retained distribution with removed/broken dependencies looks ready.
    try:
        dependencies = [Requirement(raw) for raw in cast(list[str], dist.requires or [])]
    except InvalidRequirement:
        return False
    for dependency in dependencies:
        if dependency.marker and not dependency.marker.evaluate({"extra": ""}):
            continue
        if not _installed(dependency, "", seen, lookup):
            return False
    for requested in req.extras:
        provided = {canonicalize_name(value) for value in cast(list[str], dist.metadata.get_all("Provides-Extra") or [])}
        if provided and canonicalize_name(requested) not in provided:
            return False
        matched = False
        for dependency in dependencies:
            if dependency.marker and not dependency.marker.evaluate({"extra": requested}):
                continue
            # Unconditional/base dependencies do not establish that a requested
            # extra exists when legacy metadata omits Provides-Extra.
            matched |= bool(dependency.marker and not dependency.marker.evaluate({"extra": ""}))
            if not _installed(dependency, requested, seen, lookup):
                return False
        if not matched and not provided:
            return False
    return True
