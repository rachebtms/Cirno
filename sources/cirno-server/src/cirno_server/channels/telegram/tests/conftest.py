"""Transport tests explicitly establish the owner's private destination."""

import pytest

from cirno_server.channels.telegram.binding import TelegramBinding


@pytest.fixture
def telegram_owner():
    def bind(chat_id: int = 123):
        binding = TelegramBinding()
        pin = binding.issue_pin()
        assert binding.verify(pin["pin"], user_id=chat_id, chat_id=chat_id)
        return binding

    bind()
    return bind
