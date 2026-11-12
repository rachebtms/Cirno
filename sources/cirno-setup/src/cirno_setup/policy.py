"""Installer execution options supplied by the command line."""

from dataclasses import dataclass

from cirno_setup.apt import DEFAULT_TIMEOUT


@dataclass
class Policy:
    restore_apt: bool = True
    timeout_seconds: int = DEFAULT_TIMEOUT

    def subprocess_timeout(self, *, maximum: int | None = None) -> int | None:
        """Normalize the CLI's unlimited value before applying a check limit."""
        if self.timeout_seconds == 0:
            return None
        return min(self.timeout_seconds, maximum) if maximum is not None else self.timeout_seconds
