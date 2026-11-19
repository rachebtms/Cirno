"""Required setup values must agree before and after the settings write."""

import pytest
from cirno_core.config.loader import save_config
from cirno_core.config.schema import Config
from cirno_server.channels.contracts import ChannelFieldSpec, ChannelSetupSpec, SetupRequirement
from cirno_server.channels.plugin import ChannelPlugin
from cirno_server.channels.validation import validate_channel_config
from cirno_server.features.service import channel_configured
from cirno_server.webui.settings.system import save_channel_config_values


@pytest.mark.parametrize("composite", [False, True], ids=["simple", "alternative"])
@pytest.mark.parametrize(
    "kind,value,configured",
    [
        ("bool", False, False),
        ("bool", "false", False),
        ("bool", "off", False),
        ("bool", True, True),
        ("bool", "on", True),
        ("list", [], False),
        ("list", ", , ", False),
        ("list", "one, two", True),
        ("string", "  \t ", False),
        ("secret", "false", True),
        ("int", "0", True),
        ("json", {}, False),
        ("json", "{}", False),
        ("json", '{"key": "value"}', True),
    ],
)
def test_required_value_matches_draft_saved_config_and_feature_state(
    tmp_path, monkeypatch, kind, value, configured, composite
):
    requirement = (
        SetupRequirement.one_of(("account.value", "companion"), ("fallback",))
        if composite else SetupRequirement.field("account.value")
    )
    spec = ChannelSetupSpec(
        fields={
            "account.value": ChannelFieldSpec(kind=kind),
            "companion": ChannelFieldSpec(),
            "fallback": ChannelFieldSpec(),
        },
        required=(requirement,),
    )
    plugin = ChannelPlugin(
        name="required_values", display_name="Required values",
        runtime="fixture.channel:Channel", setup=spec,
    )
    monkeypatch.setattr("cirno_server.channels.validation.load_channel_plugin", lambda _: plugin)
    path = tmp_path / "config.json"
    config = Config()
    save_config(config, path)
    draft = {"account.value": value, "companion": "present"}
    before = path.read_bytes()
    checked_draft = validate_channel_config(plugin.name, draft, config_path=path)
    assert path.read_bytes() == before
    save_channel_config_values(config, plugin.name, draft, load_channel_plugin=lambda _: plugin)
    section = getattr(config.channels, plugin.name)
    save_config(config, path)
    checked_saved = validate_channel_config(plugin.name, config_path=path)

    for checked in (checked_draft, checked_saved):
        assert checked["can_enable"] is configured
        assert checked["status"] == ("configured" if configured else "needs_setup")
        if not configured:
            assert "account.value" in checked["missing_fields"]
    assert spec.is_configured(section) is configured
    assert channel_configured(config, plugin.name, spec, plugin) is configured


def test_false_optional_toggle_is_still_exposed_in_instance_snapshot():
    from cirno_server.channels.contracts import (
        ChannelInstanceSpec,
        ChannelManagementSpec,
        channel_feature_instances,
    )

    spec = ChannelSetupSpec(fields={"useProxy": ChannelFieldSpec(kind="bool", default=True)})
    plugin = ChannelPlugin(
        name="toggle_snapshot", display_name="Toggle snapshot",
        runtime="fixture.channel:Channel", setup=spec,
        management=ChannelManagementSpec(
            multi_instance=True,
            instance_specs=lambda section, **_: [ChannelInstanceSpec("default", section)],
            update_instance_config=lambda section, values, **_: values,
        ),
    )
    snapshot = channel_feature_instances(plugin, {"useProxy": False}, setup_spec=spec)
    assert snapshot[0]["config_values"] == {"channels.toggle_snapshot.useProxy": "false"}


@pytest.mark.parametrize("default,inheritable,expected", [(None, False, "false"), (True, False, "true"), (None, True, None)])
def test_public_boolean_default_matches_runtime_without_materializing_inheritance(default, inheritable, expected):
    from cirno_server.channels.contracts import channel_default_config

    spec = ChannelSetupSpec(fields={"flag": ChannelFieldSpec(kind="bool", default=default, inheritable=inheritable)})
    plugin = ChannelPlugin(name="boolean_default", display_name="Default", runtime="fixture.channel:Channel", setup=spec)
    public = spec.to_public_dict(plugin.name)["fields"][0]
    assert public.get("default_value") == expected
    runtime_defaults = channel_default_config(plugin)
    if inheritable:
        assert "flag" not in runtime_defaults
    else:
        assert str(runtime_defaults["flag"]).lower() == expected
