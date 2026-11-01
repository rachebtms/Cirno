"""WebSocket management contract."""

from cirno.channels._manifest import field
from cirno.channels.contracts import ChannelSetupSpec
from cirno.channels.plugin import ChannelPlugin
from cirno.channels.websocket.validation import validate

SETUP_SPEC = ChannelSetupSpec(
    fields={
        "host": field(default="127.0.0.1"),
        "port": field("int", default=8765),
        "publicWsUrl": field(default=""),
        "sslCertfile": field(default=""),
        "sslKeyfile": field(default=""),
    },
    official_url="http://127.0.0.1:8765",
    validator=validate,
)

PLUGIN = ChannelPlugin(
    name="websocket",
    display_name="WebSocket",
    runtime=f"{__package__}.runtime:WebSocketChannel",
    setup=SETUP_SPEC,
    default_enabled=True,
    capabilities=frozenset({"always_enabled"}),
    webui="webui/index.ts",
)
