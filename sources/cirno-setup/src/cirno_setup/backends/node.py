"""Prefer the image's standard Node; use the official distribution outside it."""

from cirno_setup.artifacts import install_archive
from cirno_setup.context import Context
from cirno_setup.recipe import Recipe, Verification


def verify(context: Context, recipe: Recipe) -> Verification:
    result = context.inspect(["node", "--version"])
    version = result.stdout.strip().removeprefix("v").split(".")[0]
    valid = result.returncode == 0 and version.isdigit() and int(version) >= 24
    return Verification(valid, "Node.js 24+ is required")


def install(context: Context, recipe: Recipe) -> None:
    install_archive(context, "node")
