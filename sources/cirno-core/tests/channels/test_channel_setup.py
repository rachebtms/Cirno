import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import cirno.channels._setup as channel_setup_module
import cirno.channels.registry as registry_module
import pytest
from cirno.channels._setup import channel_setup_spec
from cirno.channels.plugin import ChannelPlugin, load_channel_package
from cirno.channels.registry import channel_default_enabled, discover_plugins

EXPECTED_CHANNELS = {'websocket', 'telegram'}

INTERNAL_CHANNEL_FIELDS = {'websocket': {'tokenIssueSecret', 'tokenTtlS', 'tokenIssuePath', 'sslCertfile', 'maxMessageBytes', 'host', 'publicWsUrl', 'allowFrom', 'sslKeyfile', 'trustedProxyAuth', 'pingTimeoutS', 'streaming', 'port', 'unixSocketPath', 'websocketRequiresToken', 'pingIntervalS', 'path', 'token'}}


def _flatten_channel_fields(value: object, prefix: str = "") -> set[str]:
    if not isinstance(value, dict):
        return {prefix} if prefix else set()
    if not value:
        return {prefix} if prefix else set()
    fields: set[str] = set()
    for key, nested in value.items():
        path = f"{prefix}.{key}" if prefix else key
        fields.update(_flatten_channel_fields(nested, path))
    return fields












def test_every_channel_is_a_self_contained_package() -> None:
    channel_dir = Path(channel_setup_module.__file__).parent
    package_names = {path.parent.name for path in channel_dir.glob("*/manifest.py")}

    assert package_names == EXPECTED_CHANNELS
    assert set(discover_plugins()) == EXPECTED_CHANNELS
    for name in EXPECTED_CHANNELS:
        package_dir = channel_dir / name
        assert (package_dir / "__init__.py").is_file()
        assert (package_dir / "manifest.py").is_file()
        assert (package_dir / "runtime.py").is_file()

        plugin = load_channel_package(name)
        assert plugin is not None
        assert plugin.name == name
        assert plugin.runtime.startswith(f"cirno.channels.{name}.runtime:")
        assert plugin.setup is channel_setup_spec(name)
        if plugin.webui is not None:
            assert (channel_dir.parents[1] / "cirno-web/channels" / name / plugin.webui).is_file()


def test_channel_locales_cover_authoritative_setup_contracts() -> None:
    channel_dir = Path(channel_setup_module.__file__).parent
    for name in EXPECTED_CHANNELS:
        plugin = load_channel_package(name)
        assert plugin is not None
        if plugin.webui is None or plugin.setup is None:
            continue
        english = json.loads(
            (channel_dir.parents[1] / "cirno-web/channels" / name / "webui" / "locales" / "en.json").read_text(encoding="utf-8")
        )
        setup_messages = english["setup"]
        field_messages = setup_messages.get("fields", {})
        contract_message_keys = {
            re.sub(r"[^A-Za-z0-9_-]+", "_", field_name)
            for field_name in plugin.setup.fields
        }
        assert not set(field_messages) - contract_message_keys, (
            f"{name} has locale copy for fields outside its setup contract"
        )
        for field_name, field in plugin.setup.fields.items():
            if not field.writable:
                continue
            message_key = re.sub(r"[^A-Za-z0-9_-]+", "_", field_name)
            assert message_key in field_messages, f"{name} field {field_name} has no locale copy"
        if plugin.setup.official_url:
            assert setup_messages.get("officialLabel"), f"{name} has no localized official label"


def test_every_runtime_channel_field_has_a_webui_contract() -> None:
    for name, plugin in discover_plugins().items():
        if name == "telegram":
            pytest.importorskip("telegram")
        runtime_fields = _flatten_channel_fields(plugin.load_channel_class().default_config())
        runtime_fields.discard("enabled")
        setup = plugin.setup
        assert setup is not None
        contract_fields = set(setup.fields)
        internal_fields = INTERNAL_CHANNEL_FIELDS.get(name, set())

        assert not runtime_fields - contract_fields - internal_fields, (
            f"{name} runtime fields missing from WebUI contract: "
            f"{sorted(runtime_fields - contract_fields - internal_fields)}"
        )
        assert not {
            field_name
            for field_name in runtime_fields - internal_fields
            if field_name not in setup.route_field_types
        }, f"{name} has user-configurable runtime fields that WebUI cannot save"


def test_channel_manifests_only_import_contract_modules() -> None:
    channel_dir = Path(channel_setup_module.__file__).parent
    allowed_imports = {
        "cirno.channels._manifest",
        "cirno.channels.contracts",
        "cirno.channels.plugin",
    }

    for name in EXPECTED_CHANNELS:
        manifest_path = channel_dir / name / "manifest.py"
        tree = ast.parse(manifest_path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        allowed_channel_imports = {
            module
            for module in imports
            if module.startswith(f"cirno.channels.{name}.")
            and not module.endswith(".runtime")
        }
        unexpected = imports - allowed_imports - allowed_channel_imports
        assert not unexpected, f"{name} imports runtime dependencies: {unexpected}"










def test_package_manifests_do_not_import_runtimes() -> None:
    code = f"""
import sys
from cirno.channels.plugin import load_channel_package

for name in {sorted(EXPECTED_CHANNELS)!r}:
    plugin = load_channel_package(name)
    assert plugin is not None
    assert f"cirno.channels.{{name}}.runtime" not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_channel_plugin_normalizes_webui_entry() -> None:
    plugin = ChannelPlugin(
        name="demo",
        display_name="Demo",
        runtime="example.demo.runtime:DemoChannel",
        webui="webui\\index.tsx",
    )

    assert plugin.webui == "webui/index.tsx"


def test_channel_plugin_name_must_match_package_identifier() -> None:
    with pytest.raises(ValueError, match="letters, digits, or underscores"):
        ChannelPlugin(
            name="google-chat",
            display_name="Google Chat",
            runtime="example.google_chat.runtime:GoogleChatChannel",
        )


def test_channel_plugin_rejects_invalid_runtime_import_path() -> None:
    with pytest.raises(ValueError, match="absolute import path"):
        ChannelPlugin(
            name="demo",
            display_name="Demo",
            runtime="../runtime:DemoChannel",
        )


def test_channel_default_enabled_uses_package_manifest(monkeypatch) -> None:
    plugin = ChannelPlugin(
        name="demo",
        display_name="Demo",
        runtime="example.demo.runtime:DemoChannel",
        default_enabled=True,
    )
    monkeypatch.setattr(
        registry_module,
        "load_channel_plugin",
        lambda name: plugin if name == "demo" else (_ for _ in ()).throw(ImportError()),
    )

    assert channel_default_enabled("demo") is True
    assert channel_default_enabled("missing") is False


def test_websocket_manifest_declares_the_only_default_enabled_channel() -> None:
    enabled = {
        name
        for name in EXPECTED_CHANNELS
        if (plugin := load_channel_package(name)) is not None and plugin.default_enabled
    }

    assert enabled == {"websocket"}
