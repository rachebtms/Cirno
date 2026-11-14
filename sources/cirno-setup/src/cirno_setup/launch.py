"""Container lifecycle: prepare ownership, drop privileges and exec the service."""

from __future__ import annotations

import os
import pwd

from cirno_setup.context import Context


def prepare_home(context: Context) -> None:
    instance = context.home / ".cirno"
    (instance / "state/tools").mkdir(parents=True, exist_ok=True)
    (instance / "state/cli/cache").mkdir(parents=True, exist_ok=True)
    context.run(["/usr/bin/chown", "-R", "cirno:cirno", str(instance)])


def as_user(context: Context, arguments: list[str]) -> None:
    user = pwd.getpwnam("cirno")
    command = ["/usr/bin/setpriv", f"--reuid={user.pw_uid}", f"--regid={user.pw_gid}",
               "--init-groups", str(context.service_python), "-m", "cirno_setup", *arguments]
    os.execv(command[0], command)


def start_service(context: Context, arguments: list[str]) -> None:
    # Verify the installed service independently of its configuration and never
    # contact a provider while checking readiness.
    context.run([str(context.service_python), "-c",
                 "from cirno_server.cli.entry import main; from cirno_core.agent.loop import AgentLoop"])
    custom_instance = any(arg in {"--config", "-c", "--home"} or
                          arg.startswith(("--config=", "--home=")) or
                          (arg.startswith("-c") and len(arg) > 2) for arg in arguments)
    if os.environ.get("CIRNO_DOCKER_BOOTSTRAP") == "1" and not custom_instance:
        config = context.home / ".cirno/config.json"
        context.run([str(context.service_python), "-m", "cirno_server.cli.docker_bootstrap", str(config)])
        arguments = [*arguments, "--config", str(config)]
    command = [str(context.service_python), "-m", "cirno", *arguments]
    print("[setup] Environment ready; starting Cirno", flush=True)
    os.execv(command[0], command)
