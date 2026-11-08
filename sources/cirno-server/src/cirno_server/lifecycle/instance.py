"""One process owner and restart command per instance state directory."""

from dataclasses import dataclass
from pathlib import Path

from cirno_core.config.home import get_selected_instance_path
from cirno_core.config.paths import get_data_dir
from cirno_core.runtime.processes import ProcessRuntimePaths
from cirno_server.lifecycle.contracts import ServerStartOptions


def _default_config_path() -> Path:
    return (Path.home() / ".cirno" / "config.json").resolve(strict=False)


def build_server_command(python_executable: str, options: ServerStartOptions) -> list[str]:
    """Build a foreground gateway command for process supervisors."""
    command = [
        python_executable,
        "-m",
        "cirno",
    ]
    if options.home is not None:
        command.extend(["--home", options.home])
    command.extend(
        [
            "--health-port",
            str(options.port),
        ]
    )
    if options.verbose:
        command.append("--verbose")
    if options.workspace:
        command.extend(["--workspace", options.workspace])
    if options.config_path:
        command.extend(["--config", options.config_path])
    return command


@dataclass(frozen=True)
class ServerRuntimePaths(ProcessRuntimePaths):
    """Filesystem layout for one gateway runtime instance."""

    @classmethod
    def for_instance(
        cls,
        *,
        data_dir: Path | None = None,
    ) -> "ServerRuntimePaths":
        base = data_dir or get_data_dir()
        run_dir = base / "run"
        logs_dir = base / "logs"
        stem = "gateway"
        return cls(
            run_dir=run_dir,
            logs_dir=logs_dir,
            state_path=run_dir / f"{stem}.json",
            log_path=logs_dir / f"{stem}.log",
        )


@dataclass(frozen=True)
class ServerInstance:
    """One stable local gateway identity and its child-process selectors."""

    config_path: Path
    workspace: str | None
    paths: ServerRuntimePaths
    home: Path | None = None

    @classmethod
    def resolve(
        cls,
        *,
        config_path: str | Path,
        workspace: str | None = None,
    ) -> "ServerInstance":
        resolved_config = Path(config_path).expanduser().resolve(strict=False)
        resolved_workspace = (
            str(Path(workspace).expanduser().resolve(strict=False)) if workspace else None
        )
        # One state directory has one process owner, regardless of config filename.
        return cls(
            home=get_selected_instance_path(),
            config_path=resolved_config,
            workspace=resolved_workspace,
            paths=ServerRuntimePaths.for_instance(
                data_dir=resolved_config.parent / "state",
            ),
        )

    def start_options(
        self,
        *,
        port: int,
        verbose: bool = False,
    ) -> ServerStartOptions:
        return ServerStartOptions(
            home=str(self.home) if self.home is not None else None,
            port=port,
            verbose=verbose,
            workspace=self.workspace,
            config_path=(
                None if self.config_path == _default_config_path() else str(self.config_path)
            ),
        )
