"""Python tools and channel/service packages use separate environments."""

import json
from email.message import Message
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from cirno_setup.context import Context
from cirno_setup.python import package_command
from cirno_setup.recipe import Recipe, Verification
from cirno_setup.requirements import requirement_installed


def interpreter(context: Context, recipe: Recipe) -> Path:
    return context.service_python if recipe.target == "service" else context.python


def requested_requirements(context: Context, recipe: Recipe) -> list[str]:
    # Carry the roots already encountered in this plan into each uv solve.
    # Later components may require backtracking an earlier package version;
    # resolving only the new component can silently break a selected tool.
    requested = context.python_requirements.setdefault(str(interpreter(context, recipe)), [])
    for requirement in recipe.packages:
        if requirement not in requested:
            requested.append(requirement)
    return requested


def verify(context: Context, recipe: Recipe) -> Verification:
    requested_requirements(context, recipe)
    requirements = [req for raw in recipe.packages if not (req := Requirement(raw)).marker or req.marker.evaluate()]
    script = (
        "import importlib, importlib.metadata as m, json, sys; "
        "[importlib.import_module(name) for name in json.loads(sys.argv[1])]; "
        "print(json.dumps([[d.metadata['Name'],d.version,d.requires,d.metadata.get_all('Provides-Extra')] for d in m.distributions()]))"
    )
    process = context.inspect([
        str(interpreter(context, recipe)), "-c", script, json.dumps(recipe.imports),
    ], env_override={"PYTHONPATH": ""})
    if process.returncode:
        return Verification(False, process.stderr.strip()[-1000:])
    distributions: dict[str, Any] = {}
    for name, version, requires, extras in json.loads(process.stdout):
        metadata = Message()
        for extra in cast(list[str], extras or []):
            metadata["Provides-Extra"] = extra
        distributions.setdefault(canonicalize_name(name), SimpleNamespace(version=version, requires=requires, metadata=metadata))

    def lookup(name: str) -> Any:
        try:
            return distributions[canonicalize_name(name)]
        except KeyError:
            raise PackageNotFoundError(name) from None

    valid = all((interpreter(context, recipe).parent / name).is_file() for name in recipe.commands)
    valid = valid and all(requirement_installed(str(req), lookup=lookup) for req in requirements)
    return Verification(valid, "" if valid else "Python package, requested extra or executable is missing or incompatible")


def install(context: Context, recipe: Recipe) -> None:
    arguments = [*(argument for raw in recipe.packages for argument in ("--reinstall-package", Requirement(raw).name)), *requested_requirements(context, recipe)]
    context.run(package_command("install", interpreter(context, recipe), arguments), env_override={"PYTHONPATH": ""})
