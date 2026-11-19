"""npm recipes share one managed Node and one managed npm prefix."""

import json
import os

from cirno_setup.context import Context
from cirno_setup.recipe import Recipe, Verification


def verify(context: Context, recipe: Recipe) -> Verification:
    for specification in recipe.packages:
        name, separator, version = specification.rpartition("@")
        if not separator or not name:
            name, version = specification, ""
        metadata = context.root / "npm/lib/node_modules" / name / "package.json"
        if not metadata.is_file():
            return Verification(False, f"Missing npm package: {name}")
        try:
            package = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return Verification(False, f"Unreadable npm package metadata: {name}")
        installed_version = package.get("version") if isinstance(package, dict) else None
        if not isinstance(installed_version, str) or not installed_version.strip():
            return Verification(False, f"Incomplete npm package metadata: {name}")
        if version and installed_version != version:
            return Verification(False, f"npm version differs: {name}")
    valid = all((path := context.root / "npm/bin" / name).is_file() and os.access(path, os.X_OK)
                for name in recipe.commands)
    return Verification(valid, "" if valid else "Missing npm executable")


def install(context: Context, recipe: Recipe) -> None:
    context.run(["npm", "install", "--global", "--prefix",
                 str(context.root / "npm"), *recipe.packages])
