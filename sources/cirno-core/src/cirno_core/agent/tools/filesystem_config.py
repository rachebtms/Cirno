"""Filesystem configuration shared by the tools and root schema."""

from cirno_core.config.base import Base


class FileToolsConfig(Base):
    """Filesystem tools configuration."""

    enable: bool = True
