"""Install the official nvm tree in NVM_DIR without removing user Node versions."""

import shutil
import tarfile
import tempfile

from cirno_setup.artifacts import download
from cirno_setup.context import Context
from cirno_setup.recipe import Recipe, Verification


def verify(context: Context, recipe: Recipe) -> Verification:
    script = context.root / "nvm/nvm.sh"
    if not script.is_file():
        return Verification(False, "nvm.sh is missing")
    result = context.inspect(["/bin/bash", "-c", '. "$1"; nvm --version', "setup", str(script)])
    return Verification(result.returncode == 0 and result.stdout.strip() == context.artifacts["nvm"]["version"], result.stderr.strip())


def install(context: Context, recipe: Recipe) -> None:
    artifact = context.artifacts["nvm"][context.architecture]
    archive = download(context, artifact["url"], artifact["sha256"])
    with tempfile.TemporaryDirectory() as temporary:
        with tarfile.open(archive) as package:
            package.extractall(temporary, filter="data")
        from pathlib import Path

        [source] = Path(temporary).iterdir()
        shutil.copytree(source, context.root / "nvm", dirs_exist_ok=True)
