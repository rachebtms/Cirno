"""Maintain the persistent Agent environment without changing service packages."""

from importlib.resources import files
from pathlib import Path

from cirno_setup.context import Context
from cirno_setup.python import package_command, venv_command


def initialize(context: Context) -> None:
    environment = context.root / "python"
    upgrading = (environment / "pyvenv.cfg").is_file()
    running_in_target = context.service_python.absolute() == context.python.absolute()
    if not upgrading or not running_in_target:
        context.run(venv_command(context.service_python, environment))
    # Remove only the prototype's path injection. Standard packages installed
    # in this virtual environment stay owned by uv and retain their entrypoints.
    context.run([str(context.python), "-c",
        "import sysconfig; from pathlib import Path; "
        "(Path(sysconfig.get_path('purelib'))/'cirno-bundled-tools.pth').unlink(missing_ok=True)"])
    if context.inspect([str(context.python), "-c", "import pip"]).returncode:
        wheels = Path("/usr/share/python-wheels")
        if not wheels.is_dir():
            wheels = Path(str(files("ensurepip").joinpath("_bundled")))
        context.run(package_command("install", context.python, ["--no-index", "--find-links", str(wheels), "pip"]))
    for name in ("bin", "npm", "nvm"):
        (context.root / name).mkdir(parents=True, exist_ok=True)
    cli = context.home / ".cirno/state/cli"
    for name in ("config", "data", "cache"):
        (cli / name).mkdir(parents=True, exist_ok=True)
    aliases = {".config": cli / "config", **{
        f".{name}": cli / name for name in ("xurl", "ssh", "summarize", "mcporter", "aws", "cargo", "local")
    }}
    for name, destination in aliases.items():
        destination.mkdir(parents=True, exist_ok=True)
        if name != ".config":
            destination.chmod(0o700)
        link = context.home / name
        if not link.exists() and not link.is_symlink():
            link.symlink_to(destination, target_is_directory=True)
    for name in ("git-credentials", "netrc"):
        destination = cli / name
        if not destination.exists():
            destination.touch(mode=0o600)
        link = context.home / f".{name}"
        if not link.exists() and not link.is_symlink():
            link.symlink_to(destination)
