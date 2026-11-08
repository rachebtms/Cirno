"""Personal-account policy shared by message and stream delivery."""

from collections.abc import Mapping
from typing import Any

from cirno_core.bus.delivery import DeliveryRejectedError

from .binding import TelegramBinding


def personal_chat_id(chat_id: str, metadata: Mapping[str, Any]) -> int:
    try:
        identifier = int(chat_id)
    except ValueError:
        raise DeliveryRejectedError("Invalid Telegram chat_id") from None
    if identifier <= 0:
        raise DeliveryRejectedError("Telegram supports private chats only")
    binding = TelegramBinding().status()
    if not binding["bound"]:
        raise DeliveryRejectedError("Bind your personal Telegram account before delivery")
    if not binding["enabled"] or binding["chat_id"] != chat_id:
        raise DeliveryRejectedError("Telegram delivery must target the enabled personal account")
    if binding_id := metadata.get("_telegram_binding"):
        if (
            binding["id"] != binding_id
            or metadata.get("_telegram_category") not in binding["notifications"]
        ):
            raise DeliveryRejectedError("Telegram binding or notification preference changed")
    return identifier
