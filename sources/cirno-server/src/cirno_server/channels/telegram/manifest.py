"""Telegram management contract."""

from cirno_setup.contracts.telegram import REQUIREMENTS

from cirno_server.channels._manifest import field, required
from cirno_server.channels.contracts import ChannelSetupSpec
from cirno_server.channels.plugin import ChannelPlugin
from cirno_server.channels.telegram.validation import validate

SETUP_SPEC = ChannelSetupSpec(
    fields={
        "token": field("secret"),
        "useProxy": field("bool", default=False),
        "mode": field("enum", choices={"polling", "webhook"}, default="polling"),
        "replyToMessage": field("bool", default=False),
        "reactEmoji": field(default="👀"),
        "connectionPoolSize": field("int", default=32),
        "poolTimeout": field("float", default=5.0),
        "streaming": field("bool", default=True),
        "inlineKeyboards": field("bool", default=False),
        "richMessages": field("bool", default=False),
        "streamEditInterval": field("float", default=0.6),
        "webhookUrl": field(),
        "webhookListenHost": field(default="127.0.0.1"),
        "webhookListenPort": field("int", default=8081),
        "webhookPath": field(default="/telegram"),
        "webhookSecretToken": field("secret"),
        "webhookMaxConnections": field("int", default=4),
    },
    required=(required("token"),),
    official_url="https://t.me/BotFather",
    validator=validate,
    verifies_connection=True,
)

PLUGIN = ChannelPlugin(
    name="telegram",
    display_name="Telegram",
    runtime=f"{__package__}.runtime:TelegramChannel",
    setup=SETUP_SPEC,
    dependencies=REQUIREMENTS,
    webui="webui/index.ts",
)
