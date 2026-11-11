"""Homebrew formula recipes reuse the persistent Linuxbrew prefix."""

from pathlib import Path

from cirno_setup.context import Context
from cirno_setup.recipe import Recipe, Verification

PREFIX = Path("/home/linuxbrew/.linuxbrew")


def verify(context: Context, recipe: Recipe) -> Verification:
    valid = all(list((PREFIX / "Cellar" / name.rsplit("/", 1)[-1]).glob("*/INSTALL_RECEIPT.json"))
                for name in recipe.packages)
    valid = valid and all((PREFIX / "bin" / name).is_file() for name in recipe.commands)
    return Verification(valid, "" if valid else "Missing Homebrew formula or executable")


def install(context: Context, recipe: Recipe) -> None:
    missing = [name for name in recipe.packages
               if not list((PREFIX / "Cellar" / name.rsplit("/", 1)[-1]).glob("*/INSTALL_RECEIPT.json"))]
    if missing:
        context.run([str(PREFIX / "bin/brew"), "install", *missing])
    elif not verify(context, recipe).ready:
        context.run([str(PREFIX / "bin/brew"), "reinstall", *recipe.packages])
