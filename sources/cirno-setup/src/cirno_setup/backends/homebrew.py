"""Homebrew itself is one dependency, independent of formula selection."""

import os
import shutil

from cirno_setup.backends.brew import PREFIX
from cirno_setup.context import Context
from cirno_setup.recipe import Recipe, Verification


def verify(context: Context, recipe: Recipe) -> Verification:
    command = PREFIX / "bin/brew"
    valid = command.is_file() and os.access(command, os.X_OK)
    return Verification(valid, "" if valid else "Homebrew executable is missing or not executable")


def install(context: Context, recipe: Recipe) -> None:
    repository = PREFIX / "Homebrew"
    if not (repository / "bin/brew").is_file():
        if repository.exists():
            shutil.rmtree(repository)
        context.run(["/usr/bin/git", "clone", "--depth", "1", "--branch",
                     context.artifacts["homebrew"]["version"], "https://github.com/Homebrew/brew",
                     str(repository)])
    script = repository / "bin/brew"
    script.chmod(script.stat().st_mode | 0o100)
    (PREFIX / "bin").mkdir(parents=True, exist_ok=True)
    command = PREFIX / "bin/brew"
    if not command.exists():
        command.symlink_to("../Homebrew/bin/brew")
