"""Channels configuration models."""

from __future__ import annotations

from cirno_core.config.base import Base
from pydantic import ConfigDict, Field


class ChannelsConfig(Base):
    """Configuration for chat channels.

    Built-in and plugin channel configs are stored as extra fields (dicts).
    Each channel parses its own config in __init__.
    Per-channel "streaming": true enables streaming output (requires send_delta impl).
    """

    model_config = ConfigDict(extra="allow")

    send_progress: bool = True  # stream agent's text progress to the channel
    send_tool_hints: bool = True  # stream tool-call hints (e.g. read_file("…"))
    show_reasoning: bool = True  # surface model reasoning when channel implements it
    show_compaction_notices: bool = (
        False  # automatic compaction chat notices, not UI lifecycle events
    )
    send_max_retries: int = Field(
        default=3, ge=0, le=10
    )  # Max delivery attempts (initial send included)
