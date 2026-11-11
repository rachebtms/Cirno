"""npm recipes share one managed Node and one managed npm prefix."""

import json

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
        if version and json.loads(metadata.read_text())["version"] != version:
            return Verification(False, f"npm version differs: {name}")
    valid = all((context.root / "npm/bin" / name).is_file() for name in recipe.commands)
    return Verification(valid, "" if valid else "Missing npm executable")


def install(context: Context, recipe: Recipe) -> None:
    context.run(["npm", "install", "--global", "--prefix",
                 str(context.root / "npm"), *recipe.packages])
