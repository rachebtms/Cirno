"""Installer execution options supplied by the command line."""

from dataclasses import dataclass

from cirno_setup.apt import DEFAULT_TIMEOUT


@dataclass
class Policy:
    restore_apt: bool = True
    timeout_seconds: int = DEFAULT_TIMEOUT
