"""Runtime log visibility controls shared by CLI commands."""

from loguru import logger

__all__ = ["_set_cirno_logs"]


def _set_cirno_logs(enabled: bool) -> None:
    if enabled:
        logger.enable("cirno")
    else:
        logger.disable("cirno")
