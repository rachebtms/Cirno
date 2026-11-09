"""Build one remote Bash session with a consistent directory and environment."""

import shlex

from cirno_core.credentials.ssh_session import SSHSessionSettings


def remote_path(path: str) -> str:
    if path == "~":
        return '"$HOME"'
    if path.startswith("~/"):
        return '"$HOME"/' + shlex.quote(path[2:])
    return shlex.quote(path)


def remote_shell(settings: SSHSessionSettings, command: str = "", *, interactive: bool = False) -> str:
    setup = [f"export {name}={shlex.quote(value)}" for name, value in settings.environment.items()]
    setup.append(f"cd -- {remote_path(settings.working_directory)} || exit $?")
    if settings.init_script:
        script_path = settings.init_script if "/" in settings.init_script else "./" + settings.init_script
        setup.append(f". {remote_path(script_path)} >&2 || exit $?")
    script = "\n".join(setup) + "\n" + command
    if interactive:
        script = '[ ! -f "$HOME/.bashrc" ] || . "$HOME/.bashrc"\n' + script
        script = "exec bash --rcfile <(printf %s " + shlex.quote(script) + ") -i"
    return "bash -lc " + shlex.quote(script)
