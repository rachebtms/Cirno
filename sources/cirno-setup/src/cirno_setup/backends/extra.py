"""Read optional service dependencies from installed distribution metadata."""

import json

from cirno_setup.backends import pip
from cirno_setup.context import Context
from cirno_setup.recipe import Recipe, Verification


def expanded(context: Context, recipe: Recipe) -> Recipe:
    distribution, extra = recipe.packages[0].split(":", 1)
    script = (
        "import importlib.metadata as m,json,sys; from packaging.requirements import Requirement; "
        "name,extra=sys.argv[1:]; result=[]; "
        "\nfor raw in m.requires(name) or []:\n"
        " r=Requirement(raw)\n"
        " if r.marker and r.marker.evaluate({'extra':extra}):\n"
        "  r.marker=None; result.append(str(r))\n"
        "print(json.dumps(result))"
    )
    process = context.run([str(context.service_python), "-c", script, distribution, extra], capture=True, env_override={"PYTHONPATH": ""})
    return Recipe("pip", tuple(json.loads(process.stdout)), imports=recipe.imports, target="service")


def verify(context: Context, recipe: Recipe) -> Verification:
    return pip.verify(context, expanded(context, recipe))


def install(context: Context, recipe: Recipe) -> None:
    pip.install(context, expanded(context, recipe))
