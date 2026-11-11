"""System packages are installed only during the privileged setup phase."""

from cirno_setup import apt
from cirno_setup.context import Context
from cirno_setup.recipe import Recipe, Verification


def verify(context: Context, recipe: Recipe) -> Verification:
    installed = apt.installed_packages()
    missing: list[str] = []
    for specification in recipe.packages:
        name, _, version = specification.partition("=")
        if name not in installed or (version and installed[name] != version):
            missing.append(specification)
    return Verification(not missing, ", ".join(missing))


def install(context: Context, recipe: Recipe) -> None:
    apt.install(context, list(recipe.packages), managed=True)
