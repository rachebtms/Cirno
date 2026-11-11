"""Privileged preparation uses only the immutable setup installation."""

import os

from cirno_setup import apt
from cirno_setup.backends.brew import PREFIX
from cirno_setup.context import Context
from cirno_setup.planner import Step


def prepare(context: Context, steps: list[Step]) -> None:
    if any(step.recipe.provider in {"homebrew", "brew"} for step in steps):
        storage = context.root / "homebrew"
        if not storage.resolve().is_relative_to(context.root.resolve()):
            raise ValueError("Homebrew storage must stay inside the instance")
        storage.mkdir(parents=True, exist_ok=True)
        PREFIX.mkdir(parents=True, exist_ok=True)
        if not PREFIX.samefile(storage):
            if PREFIX.is_symlink() or any(PREFIX.iterdir()):
                raise RuntimeError("Mount state/tools/homebrew at /home/linuxbrew/.linuxbrew")
            PREFIX.rmdir()
            PREFIX.symlink_to(storage, target_is_directory=True)
        owner = (context.home / ".cirno").stat()
        os.chown(storage, owner.st_uid, owner.st_gid, follow_symlinks=False)
    apt.configure_cache(context)
    apt.observe(context)
    apt.restore(context)


def hand_over_state(context: Context) -> None:
    owner = (context.home / ".cirno").stat()
    for name in ("setup.json", "setup.lock"):
        path = context.root / name
        if path.exists():
            os.chown(path, owner.st_uid, owner.st_gid, follow_symlinks=False)
