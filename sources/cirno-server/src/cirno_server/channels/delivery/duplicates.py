"""Bounded duplicate detection scoped to an upstream message identity."""

from __future__ import annotations

import hashlib
from collections import OrderedDict

from cirno_core.bus.events import OUTBOUND_META_AGENT_UI, OutboundMessage

FINGERPRINT_LIMIT = 1000


class OriginReplies:
    def __init__(self) -> None:
        self.fingerprints: OrderedDict[tuple[str, str, str], str] = OrderedDict()

    @staticmethod
    def fingerprint(content: str) -> str:
        # Indentation, line breaks and spaces can change code or document meaning.
        return hashlib.sha1(content.encode("utf-8")).hexdigest() if content.strip() else ""

    def remember(
        self,
        key: tuple[str, str, str],
        fingerprint: str,
    ) -> None:
        self.fingerprints[key] = fingerprint
        self.fingerprints.move_to_end(key)
        while len(self.fingerprints) > FINGERPRINT_LIMIT:
            self.fingerprints.popitem(last=False)

    def matches(self, msg: OutboundMessage) -> bool:
        metadata = msg.metadata or {}
        if (
            msg.event is not None or msg.media or msg.buttons or msg.reply_to is not None
            or any(key in metadata for key in (
                OUTBOUND_META_AGENT_UI, "_telegram_action_url", "_telegram_action_label", "render_as",
            ))
        ):
            # A caption cannot identify an attachment (a file path may have been
            # overwritten), button action or lifecycle event. Their owners keep
            # their own delivery identities; do not drop them by text alone.
            return False
        fingerprint = self.fingerprint(msg.content)
        if not fingerprint:
            return False

        origin_message_id = metadata.get("origin_message_id")
        if isinstance(origin_message_id, str) and origin_message_id:
            key = (msg.channel, msg.chat_id, origin_message_id)
            if self.fingerprints.get(key) == fingerprint:
                self.fingerprints.move_to_end(key)
                return True
            self.remember(key, fingerprint)

        message_id = metadata.get("message_id")
        if isinstance(message_id, str) and message_id:
            key = (msg.channel, msg.chat_id, message_id)
            self.remember(key, fingerprint)

        return False
