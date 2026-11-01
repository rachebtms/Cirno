"""Message bus module for decoupled channel-agent communication."""

from importlib import import_module

_EXPORTS = {
    "InboundMessage": "cirno.bus.events",
    "OutboundMessage": "cirno.bus.events",
    "MessageBus": "cirno.bus.queue",
}


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(_EXPORTS[name]), name)
    globals()[name] = value
    return value

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
