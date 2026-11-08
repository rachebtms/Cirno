"""Cirno's project catalog and conversation organization tools."""

import json

from cirno_core.agent.tools.base import Tool, ToolResult, tool_parameters
from cirno_core.agent.tools.context import current_request_context
from cirno_core.agent.tools.schema import ObjectSchema, StringSchema
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.session_handles import SessionHandleResolver


@tool_parameters(ObjectSchema({
    "action": StringSchema(enum=("list", "get", "create", "update", "assign", "delete")),
    "id": StringSchema("Project ID returned by projects.list or projects.create.", min_length=1),
    "name": StringSchema("Project name; independent of its working directory.", min_length=1, max_length=120),
    "description": StringSchema("Project purpose or notes.", max_length=4000),
    "working_directory": StringSchema("Optional default working directory. Does not move files or reconfigure existing conversations.", max_length=4096),
    "to": StringSchema("Stable conversation id (preferred) or current @name to move into or out of a Project.", min_length=1),
    "project_id": StringSchema("Destination Project ID. Pass null to remove membership.", min_length=1, nullable=True),
}, required=["action"], additional_properties=False).to_json_schema())
class ProjectsTool(Tool):
    @classmethod
    def enabled(cls, ctx):
        return ctx.sessions is not None

    @classmethod
    def create(cls, ctx):
        return cls(ctx.sessions, ctx.bus)

    def __init__(self, sessions, bus=None):
        self.sessions, self.bus = sessions, bus

    @property
    def name(self):
        return "project"

    @property
    def description(self):
        return "Router only: list, inspect, create, update and delete Projects, or move conversations between them. Deleting a Project preserves its conversations, history, memory and files. Assignment changes membership, not the working directory."

    async def execute(self, action, to=None, **values):
        request = current_request_context()
        if request is None or request.session_key != ROUTER_SESSION_KEY:
            return ToolResult.error("Only the Router may manage Projects through tools.")
        header = await self.sessions.state.read_header(request.session_key)
        if header is None or request.session_generation and request.session_generation != header.generation:
            return ToolResult.error("The Router conversation was cleared or replaced; no Project was changed.")
        if action == "assign":
            handle = await SessionHandleResolver(self.sessions).aresolve(to)
            if handle is None:
                return ToolResult.error(f"Conversation not found: {to}")
            values["session_key"] = handle.session_key
            if "project_id" not in values:
                return ToolResult.error("project_id is required; pass null to remove Project membership.")
        return json.dumps(await self.sessions.projects.action(action, values, bus=self.bus), ensure_ascii=False)
