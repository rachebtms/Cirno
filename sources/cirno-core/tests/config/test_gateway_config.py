import pytest

from cirno_core.config.schema import Config
from cirno_core.config.server import ServerConfig


def test_gateway_restart_mode_accepts_camel_alias():
    config = Config.model_validate({"server": {"restartMode": "exit"}})

    assert config.server.restart_mode == "exit"
    assert config.model_dump(by_alias=True)["server"]["restartMode"] == "exit"


def test_gateway_restart_mode_rejects_unknown_value():
    with pytest.raises(ValueError):
        ServerConfig(restart_mode="service")
