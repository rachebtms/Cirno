import sys
from importlib.metadata import entry_points
from types import ModuleType
from unittest.mock import MagicMock, patch


from cirno.agent.tools.base import Tool
from cirno.agent.tools.loader import ToolLoader


def test_loader_discovers_entry_point_tools(tmp_path, monkeypatch):
    """Discover a real distribution descriptor in the tool entry-point group."""

    class _FakeTool(Tool):
        __name__ = "FakeTool"
        _plugin_discoverable = True
        _scopes = {"core"}

        @property
        def name(self) -> str:
            return "fake_tool"

        @property
        def description(self) -> str:
            return "A fake tool for testing."

        @property
        def parameters(self) -> dict:
            return {"type": "object"}

        @classmethod
        def enabled(cls, ctx):
            return True

        @classmethod
        def create(cls, ctx):
            return MagicMock()

        async def execute(self, **_):
            return "ok"

    plugin = ModuleType("test_tool_plugin")
    monkeypatch.setattr(plugin, "FakeTool", _FakeTool, raising=False)
    monkeypatch.setitem(sys.modules, plugin.__name__, plugin)
    distribution = tmp_path / "test_tool_plugin-1.0.dist-info"
    distribution.mkdir()
    (distribution / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: test-tool-plugin\nVersion: 1.0\n", encoding="utf-8",
    )
    (distribution / "entry_points.txt").write_text(
        "[cirno.tools]\nmy_plugin = test_tool_plugin:FakeTool\n"
        "[other.tools]\nother_plugin = test_tool_plugin:FakeTool\n", encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr("cirno.agent.tools.loader.entry_points", entry_points)
    discovered = ToolLoader()._discover_plugins()

    assert "my_plugin" in discovered
    assert discovered["my_plugin"] is _FakeTool
    assert "other_plugin" not in discovered


def test_loader_skips_abstract_entry_point_tools():
    """Verify abstract tool classes registered via entry_points are skipped."""
    mock_ep = MagicMock()
    mock_ep.name = "abstract_plugin"

    class _AbstractTool(Tool):
        __name__ = "AbstractTool"
        _plugin_discoverable = True
        _scopes = {"core"}

        @classmethod
        def enabled(cls, ctx):
            return True

        @classmethod
        def create(cls, ctx):
            return MagicMock()

        # Intentionally missing abstract properties (name, description, parameters, execute)

    mock_ep.load.return_value = _AbstractTool

    with patch("cirno.agent.tools.loader.entry_points", return_value=[mock_ep]):
        loader = ToolLoader()
        discovered = loader._discover_plugins()

    assert "abstract_plugin" not in discovered
