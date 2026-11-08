"""Service process and health contracts."""

from dataclasses import dataclass
from typing import Literal

from cirno_core.runtime.processes import ProcessResult, ProcessStartOptions, ProcessStatus

ServerLaunchMode = Literal["foreground", "background", "unknown"]


@dataclass(frozen=True)
class ServerStartOptions(ProcessStartOptions):
    """Server launch options, including the explicit instance root."""

    home: str | None = None


@dataclass(frozen=True)
class ServerHealthIdentity:
    """Opaque local instance/run identity; never configuration paths or credentials."""

    instance_id: str
    run_id: str
    version: str


@dataclass(frozen=True)
class ServerStatus(ProcessStatus):
    """Observable lifecycle state for one shared local gateway."""

    launch_mode: ServerLaunchMode = "unknown"
    ready: bool | None = None


@dataclass(frozen=True)
class RuntimeResult(ProcessResult):
    """Result of a gateway lifecycle operation."""

    status: ServerStatus
    promoted: bool = False


class ServerAlreadyRunningError(RuntimeError):
    """Raised when a foreground gateway tries to replace a live instance."""

    def __init__(self, status: ServerStatus) -> None:
        super().__init__("server_already_running")
        self.status = status
