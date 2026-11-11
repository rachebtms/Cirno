"""Homebrew itself is one dependency, independent of formula selection."""

import shutil

from cirno_setup.backends.brew import PREFIX
from cirno_setup.context import Context
from cirno_setup.recipe import Recipe, Verification


def verify(context: Context, recipe: Recipe) -> Verification:
    return Verification((PREFIX / "bin/brew").is_file(), "Homebrew is not installed")


def install(context: Context, recipe: Recipe) -> None:
    repository = PREFIX / "Homebrew"
    if not (repository / "bin/brew").is_file():
        if repository.exists():
            shutil.rmtree(repository)
        context.run(["/usr/bin/git", "clone", "--depth", "1", "--branch",
                     context.artifacts["homebrew"]["version"], "https://github.com/Homebrew/brew",
                     str(repository)])
    (PREFIX / "bin").mkdir(parents=True, exist_ok=True)
    command = PREFIX / "bin/brew"
    if not command.exists():
        command.symlink_to("../Homebrew/bin/brew")
