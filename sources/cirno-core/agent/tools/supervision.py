"""The personal Cirno conversation's bounded supervisory tool surface."""

from cirno_core.agent.tools.base import Tool, ToolResult, tool_parameters
from cirno_core.agent.tools.context import current_request_context
from cirno_core.agent.tools.schema import IntegerSchema, StringSchema, tool_parameters_schema
from cirno_core.session.goal_state import MAX_GOAL_OBJECTIVE_CHARS
from cirno_core.session.keys import CIRNO_SESSION_KEY


class _SupervisionTool(Tool):
    @classmethod
    def enabled(cls, ctx):
        return ctx.conversation_control is not None

    @classmethod
    def create(cls, ctx):
        return cls(ctx.conversation_control)

    def __init__(self, control):
        self.control = control

    async def execute(self, to, action, **values):
        request = current_request_context()
        if request is None or request.session_key != CIRNO_SESSION_KEY:
            return ToolResult.error("Only Cirno may control other conversations or their Goals.")
        return await self.control.execute(to, action, goal=self.name == "control_goal", **values)


@tool_parameters(tool_parameters_schema(
    to=StringSchema("Target conversation @handle; must be another persistent conversation.", min_length=1),
    action=StringSchema("stop cancels current execution and stops its Goal without deleting progress. continue runs from saved context, resuming a stopped Goal if present. No tool side effects are undone.", enum=("stop", "continue")),
    required=["to", "action"],
))
class ControlSessionTool(_SupervisionTool):
    @property
    def name(self):
        return "control_session"

    @property
    def description(self):
        return "Cirno only: stop or continue another conversation's execution. Control only user-authorized work. Progress and environment changes remain. Continuing a running conversation does not start a second worker."


@tool_parameters(tool_parameters_schema(
    to=StringSchema("Target conversation @handle.", min_length=1),
    action=StringSchema("get reads the Goal. create creates one; set explicitly replaces its objective. update edits recap, summary or continuation limit without resetting status/count. stop/pause/wait suspend work; resume restarts it; delete removes the Goal. Only the executing conversation declares completion.", enum=("get", "create", "set", "update", "stop", "pause", "resume", "delete", "wait")),
    objective=StringSchema("Required for create/set; authorized objective with completion criteria.", max_length=MAX_GOAL_OBJECTIVE_CHARS),
    ui_summary=StringSchema("Short Goal display label.", max_length=120),
    recap=StringSchema("Saved progress and next step.", max_length=4000),
    continuation_limit=IntegerSchema(description="Optional automatic continuation limit; 0 is unlimited. Omit to retain the configured value.", minimum=0),
    wake_after_seconds=IntegerSchema(description="Required for wait; seconds before the Goal wakes.", minimum=1),
    required=["to", "action"],
))
class ControlGoalTool(_SupervisionTool):
    @property
    def name(self):
        return "control_goal"

    @property
    def description(self):
        return "Cirno only: inspect, create, set, update, stop, pause, resume, wait or delete another conversation's Goal. Mutations stop its current worker first. Create/set/resume queue execution; update continues a previously active Goal. Suspended Goals remain suspended. Completion remains the worker's responsibility."
