"""Explicit visual inspection through the shared filesystem reader."""
from typing import Any

from cirno_core.agent.tools.base import ToolResult, tool_parameters
from cirno_core.agent.tools.filesystem.read import ReadFileTool
from cirno_core.agent.tools.schema import StringSchema, tool_parameters_schema


@tool_parameters(tool_parameters_schema(path=StringSchema("Path to the local image to add to model context"), required=["path"]))
class ViewImageTool(ReadFileTool):
    _scopes = {"core", "subagent"}

    @property
    def name(self) -> str:
        return "view_image"

    @property
    def description(self) -> str:
        return "View a local image: adds actual image pixels to the model context, not just a path. Use for screenshots, plots and photos. Requires an image-capable model."

    async def execute(self, path: str | None = None, **kwargs: Any) -> Any:
        from cirno_core.agent.tools.context import current_request_context
        request = current_request_context()
        if request and request.runtime and request.runtime.provider.media_capabilities.image is False:
            return ToolResult.error("The selected model has image input disabled. Choose an image-capable model or update its capabilities in Settings.")
        result = await super().execute(path=path)
        if isinstance(result, list) and any(block.get("type") == "image_url" for block in result):
            return result
        if isinstance(result, ToolResult) and result.is_error:
            return result
        return ToolResult.error("This file is not a supported image. Use files.read for text and documents.")
