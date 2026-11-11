"""Pinned official archives are installed with checksum verification."""

from cirno_setup.artifacts import install_archive
from cirno_setup.context import Context
from cirno_setup.recipe import Recipe, Verification


def verify(context: Context, recipe: Recipe) -> Verification:
    name = recipe.packages[0]
    executable = context.managed / name / "bin" / name
    if not executable.is_file():
        return Verification(False, f"Missing {name}")
    process = context.inspect([str(executable), "--version"])
    version = context.artifacts[name]["version"]
    ready = process.returncode == 0 and process.stdout.strip().split("\n")[0] in {
        f"v{version}", f"pandoc {version}", f"xurl version {version}", f"xurl version v{version}",
    }
    return Verification(ready, "" if ready else f"Unexpected {name} version")


def install(context: Context, recipe: Recipe) -> None:
    install_archive(context, recipe.packages[0])
