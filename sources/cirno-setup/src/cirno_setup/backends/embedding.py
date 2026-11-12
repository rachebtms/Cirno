"""The model download recipe reuses the existing revision and hash definitions."""

import os
import runpy
from pathlib import Path

from cirno_setup.artifacts import digest
from cirno_setup.context import Context
from cirno_setup.recipe import Recipe, Verification


def verify(context: Context, recipe: Recipe) -> Verification:
    module = runpy.run_path(str(context.assets / "embedding.py"))
    destination = Path(os.environ.get("CIRNO_BUNDLED_EMBEDDING_DIR", context.root / "models/bge-small-zh-v1.5"))
    for name, _, expected in module["downloads"]():
        path = destination / Path(name).name
        if not path.is_file():
            return Verification(False, f"Embedding asset is missing: {path.name}")
        if digest(path) != expected:
            return Verification(False, f"Embedding checksum mismatch: {path.name}")
    return Verification(True)


def install(context: Context, recipe: Recipe) -> None:
    destination = os.environ.get("CIRNO_BUNDLED_EMBEDDING_DIR", str(context.root / "models/bge-small-zh-v1.5"))
    context.run([str(context.service_python), str(context.assets / "embedding.py"), destination])
