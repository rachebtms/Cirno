"""Filesystem configuration shared by the tools and root schema."""

from cirno.config.base import Base


class FileToolsConfig(Base):
    """Filesystem tools configuration."""

    enable: bool = True
