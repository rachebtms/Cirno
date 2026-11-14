"""The image tool must reach a subsequent model request as visual input."""
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace
import pytest
from PIL import Image
from cirno_core.agent.runner.engine import AgentRunner
from cirno_core.agent.tools.filesystem.view_image import ViewImageTool
from cirno_core.agent.tools.filesystem.read import ReadFileTool
from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.tool_calls import ToolCallRequest
from sources.development.testing.runtime import make_run_spec


@pytest.mark.parametrize("tool_class", [ReadFileTool, ViewImageTool])
async def test_all_image_read_paths_respect_disabled_model_capability(tmp_path, tool_class):
    image = tmp_path / "chart.png"
    Image.new("RGB", (2, 2), "red").save(image)
    runtime = SimpleNamespace(provider=SimpleNamespace(media_capabilities=SimpleNamespace(image=False)))
    with request_context(RequestContext(channel="websocket", chat_id="one", session_key="websocket:one", runtime=runtime)):
        result = await tool_class(workspace=tmp_path).execute(path=str(image))
    assert result.is_error and "image input disabled" in result


async def test_view_image_adds_pixels_to_next_model_request(tmp_path):
    image = tmp_path / "chart.png"
    Image.new("RGB", (12, 10), "red").save(image)
    registry = ToolRegistry(); registry.register(ViewImageTool(workspace=tmp_path, allowed_dir=tmp_path))
    provider = MagicMock(spec=LLMProvider)
    captured = []
    async def chat(**kwargs):
        captured.append(kwargs["messages"])
        return LLMResponse(content=None, tool_calls=[ToolCallRequest(id="look", name="view_image", arguments={"path": str(image)})]) if len(captured) == 1 else LLMResponse(content="A red chart")
    provider.chat_stream_with_retry = AsyncMock(side_effect=chat)
    result = await AgentRunner().run(make_run_spec(provider, initial_messages=[{"role": "user", "content": "Inspect chart.png"}], tools=registry, model="vision", max_iterations=3, max_tool_result_chars=16000))
    assert result.final_content == "A red chart"
    image_rows = [row for row in captured[-1] if row.get("role") == "tool"]
    assert image_rows and any(block.get("type") == "image_url" and block["image_url"]["url"].startswith("data:image/png;base64,") for block in image_rows[-1]["content"])


async def test_view_image_retains_filesystem_boundary_and_rejects_nonimages(tmp_path):
    root = tmp_path / "project"; root.mkdir()
    outside = tmp_path / "outside.png"; Image.new("RGB", (2, 2), "red").save(outside)
    tool = ViewImageTool(workspace=root, allowed_dir=root)
    assert (await tool.execute(path=str(outside))).is_error
    (root / "note.txt").write_text("hello")
    assert (await tool.execute(path="note.txt")).is_error
