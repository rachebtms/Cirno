"""Node execution, source-grounded memory and inspectable Skill history."""

import json

from cirno.agent.tools.base import Tool, ToolResult, tool_parameters
from cirno.agent.tools.context import current_request_context
from cirno.agent.tools.schema import (
    ArraySchema,
    BooleanSchema,
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)
from cirno.memory.repository import MemoryRepository
from cirno.nodes.service import Nodes
from cirno.security.workspace_policy import resolve_allowed_path
from cirno.skills.history import inspect_skill


@tool_parameters(
    tool_parameters_schema(
        action=StringSchema(
            enum=["list", "execute", "upload", "download", "start", "status", "stop"]
        ),
        node_id=StringSchema("Configured Node ID."),
        command=StringSchema("Remote shell command."),
        job_id=StringSchema("Saved remote job ID."),
        local_path=StringSchema("Local file path."),
        remote_path=StringSchema("Remote file path."),
        required=["action"],
    )
)
class NodeTool(Tool):
    @classmethod
    def enabled(cls, ctx):
        return ctx.config.exec.enable

    @classmethod
    def create(cls, ctx):
        return cls()

    @property
    def name(self):
        return "node"

    @property
    def description(self):
        return "Use configured Nodes through SSH only. Execute short commands, transfer files, or start/status/stop durable remote jobs. Use start for long work; disconnecting SSH is not stopping a job. Unknown submissions must be inspected before retrying."

    async def execute(
        self,
        action,
        node_id=None,
        command=None,
        job_id=None,
        local_path=None,
        remote_path=None,
        **kwargs,
    ):
        nodes = Nodes()
        try:
            if action == "list":
                result = {"nodes": nodes.list_nodes(), "jobs": nodes.data.list("node_jobs")}
            elif action in {"execute", "start"}:
                if not node_id or not command:
                    raise ValueError("node_id and command are required")
                result = (
                    await nodes.execute(node_id, command)
                    if action == "execute"
                    else await nodes.start_job(node_id, command)
                )
            elif action in {"status", "stop"}:
                if not job_id:
                    raise ValueError("job_id is required")
                result = await nodes.inspect_job(job_id, stop=action == "stop")
            elif action in {"upload", "download"}:
                if not node_id or not local_path or not remote_path:
                    raise ValueError("node_id, local_path and remote_path are required")
                request = current_request_context()
                scope = request.workspace_scope if request else None
                path = resolve_allowed_path(
                    local_path,
                    workspace=scope.project_path if scope else None,
                    allowed_root=scope.project_path
                    if scope and scope.restrict_to_workspace
                    else None,
                    strict=action == "upload",
                )
                result = await nodes.transfer(
                    node_id, str(path), remote_path, download=action == "download"
                )
            else:
                raise ValueError("Unknown Node action")
        except (ValueError, KeyError, RuntimeError, OSError, TimeoutError) as exc:
            return ToolResult.error(str(exc))
        return json.dumps(result, ensure_ascii=False)


@tool_parameters(
    tool_parameters_schema(
        action=StringSchema(enum=["save", "update", "search", "read", "source", "history", "link", "checkpoint", "status", "tags", "confirm"]),
        content=StringSchema("Atomic memory or task checkpoint: objective, completed work, blockers, next steps and exact artifact references.", max_length=64000),
        source=StringSchema("Exact evidence URI, path, conversation reference or memory:<id>. Never invent sources."),
        scope=StringSchema(enum=["session", "project", "user", "all"]),
        kind=StringSchema(enum=["observation", "hypothesis", "fact", "lesson"]),
        layer=StringSchema(enum=["event", "knowledge", "task", "source", "profile", "all"]),
        title=StringSchema(max_length=160),
        tags=ArraySchema(StringSchema(max_length=80), max_items=20),
        mode=StringSchema(enum=["bm25", "semantic", "hybrid"], description="BM25 by default. Semantic/hybrid explicitly starts the optional CPU worker for distilled knowledge; no reranker."),
        query=StringSchema("BM25 query in Chinese or English, or exact memory ID."),
        memory_id=StringSchema("Memory ID to read or update."),
        based_on=StringSchema("Evidence memory ID. Derived memory inherits its visibility scope."),
        expected_revision=IntegerSchema(minimum=1, description="Revision read before editing; protects concurrent edits."),
        target_id=StringSchema("Target memory ID for a link."),
        relation=StringSchema(enum=["supports", "conflicts", "supersedes", "related", "derived_from"]),
        include_history=BooleanSchema(description="Include superseded/archived records in search."),
        revision=IntegerSchema(minimum=1),
        limit=IntegerSchema(minimum=1, maximum=30),
        offset=IntegerSchema(minimum=0),
        start_line=IntegerSchema(minimum=1),
        char_offset=IntegerSchema(minimum=0, description="Continue a truncated source line at next_char_offset."),
        purpose=StringSchema(enum=["knowledge", "evidence", "all"], description="Default knowledge recalls distilled findings/checkpoints/profiles. Use evidence explicitly to verify raw messages and exact claims."),
        expand_links=IntegerSchema(minimum=0, maximum=10, description="One-hop evidence/correction neighbors, bounded across all results; default 3."),
        time_field=StringSchema(enum=["observed_at", "created_at", "updated_at"]),
        time_zone=StringSchema("IANA timezone for date-only/naive bounds; defaults to the configured timezone."),
        observed_at=StringSchema("When the event happened, in ISO format, preferably with timezone. Do not invent a date."),
        since=StringSchema("Inclusive ISO time/date lower bound; event occurrence time by default."),
        until=StringSchema("Inclusive ISO time/date upper bound; a date includes that entire day."),
        input_revision=IntegerSchema(minimum=1),
        outcome=StringSchema(enum=["created", "merged", "skipped", "failed"]),
        target_ids=ArraySchema(StringSchema(), max_items=10),
        reason=StringSchema("Dream per-input disposition and evidence explanation; required for confirmation."),
        required=["action"],
    )
)
class MemoryTool(Tool):
    @classmethod
    def enabled(cls, ctx):
        return ctx.sessions is not None

    @classmethod
    def create(cls, ctx):
        return cls(ctx.sessions)

    def __init__(self, sessions=None, *, maintenance=False, owner_access=None, evidence_ids=None, batch_token=None):
        self.sessions = sessions
        self.maintenance = maintenance
        self.owner_access = owner_access
        self.evidence_ids = evidence_ids
        self.batch_token = batch_token

    @property
    def name(self):
        return "memory"

    @property
    def description(self):
        return ("Search source-grounded layered memory with BM25 before answering about past decisions, precise values or results. "
                "Read returned IDs and original sources to verify claims; do not guess from summaries. "
                "Save atomic observations/hypotheses/facts with sources, or checkpoint long work at milestones and before compaction. "
                "Use expected_revision to update, history to inspect old versions, and link(supersedes) for evidence-backed corrections. "
                "Default search returns knowledge, task checkpoints and profiles. If empty, search purpose=evidence for recent unprocessed events or archived originals; use tags to discover tags, "
                "and time_field=observed_at for event dates (unknown dates are excluded). Bounded neighbors show corrections. "
                "Dream must confirm each input using its revision, outcome, target_ids and reason; normal execution cannot confirm Dream batches. "
                "MEMORY.md remains injected; searching is on demand, not automatic on every reply.")

    async def execute(self, action, content="", source="", scope=None, kind=None, query="",
                      memory_id=None, layer=None, title="", tags=None, based_on=None, expected_revision=None,
                      target_id=None, relation="related", include_history=False, revision=None, limit=10,
                      offset=0, start_line=1, char_offset=0, mode="bm25", since=None, until=None,
                      purpose="knowledge", expand_links=3, time_field="observed_at", time_zone=None, observed_at=None,
                      input_revision=None, outcome=None, target_ids=None, reason="", **kwargs):
        import asyncio
        request = current_request_context()
        if request is None or not request.session_key:
            return ToolResult.error("Conversation context is required")
        metadata = ((await self.sessions.state.read_metadata(request.session_key)) or {}).get("metadata", {}) if self.sessions else {}
        access = self.owner_access or dict(session_key=request.session_key, project_id=metadata.get("project_id"), maintenance=self.maintenance)
        def run():
            repo = MemoryRepository()
            repo.migrate_legacy()
            repo.sync_profiles()
            if action == "status":
                return repo.status(**access)
            if action == "tags":
                return repo.list_tags(prefix=query, limit=limit, offset=offset, **access)
            if action == "confirm":
                if not self.maintenance or not self.batch_token or memory_id not in (self.evidence_ids or set()):
                    raise ValueError("Confirmation is restricted to inputs of the current Dream batch")
                return repo.confirm(self.batch_token, memory_id, input_revision, outcome, target_ids, reason, **access)
            if action == "read":
                return repo.read(memory_id, revision=revision, **access)
            if action == "source":
                return repo.read_source(memory_id, revision=revision, start_line=start_line, char_offset=char_offset, limit=min(limit, 20), **access)
            if action == "history":
                return {"revisions": repo.history(memory_id, **access)}
            if action == "link":
                return repo.link(memory_id, target_id, relation, source, **access)
            if action == "checkpoint":
                if self.maintenance:
                    raise ValueError("Task checkpoints belong to the executing conversation, not Dream")
                return repo.checkpoint(request.session_key, content, source, project_id=access["project_id"], expected_revision=expected_revision)
            if action in {"save", "update"}:
                if layer in {"source", "profile", "all", "task"}:
                    raise ValueError("Save event/knowledge records; use checkpoint for task state. Original evidence and profiles have dedicated writers.")
                if action == "update" and not memory_id:
                    raise ValueError("memory_id and expected_revision are required to update")
                if action == "update" and repo.read(memory_id, **access)["layer"] not in {"event", "knowledge"}:
                    raise ValueError("Use action=checkpoint with expected_revision for task state. Profiles and original evidence have dedicated writers.")
                if self.maintenance and (not based_on or self.evidence_ids is not None and based_on not in self.evidence_ids):
                    raise ValueError("Dream writes require based_on from the current queued evidence batch")
                return repo.save(content, source=source, scope=scope or "session", kind=kind, layer=layer,
                                 title=title, tags=tags, memory_id=memory_id, expected_revision=expected_revision,
                                 based_on=based_on, turn_id=request.turn_id, message_id=request.message_id,
                                 enqueue=not self.maintenance, observed_at=observed_at, **access)
            if action != "search":
                raise ValueError("Unknown memory action")
            from cirno.config.loader import load_config
            config = load_config().agents.defaults
            filters = dict(scope=scope, layer=layer, tags=tags, include_history=include_history,
                           offset=offset, since=since, until=until, time_field=time_field, time_zone=time_zone or config.timezone, purpose=purpose, expand_links=expand_links, **access)
            from cirno.memory.search import search
            return search(repo, query, config.memory, mode=mode, limit=limit, **filters)
        try:
            return json.dumps(await asyncio.to_thread(run), ensure_ascii=False)
        except (ValueError, KeyError, PermissionError, OSError) as exc:
            return ToolResult.error(str(exc))


@tool_parameters(
    tool_parameters_schema(
        name=StringSchema("Skill folder name."),
        action=StringSchema(enum=["validate", "history"]),
        required=["name", "action"],
    )
)
class InspectSkillTool(Tool):
    @classmethod
    def create(cls, ctx):
        return cls()

    @property
    def name(self):
        return "inspect_skill"

    @property
    def description(self):
        return "Validate Skill metadata and Python/shell syntax without executing it; inspect historical versions in Home/skills-history. Read historical files with read_file. Restore only by deliberately editing the current Skill; there is no automatic rollback."

    async def execute(self, name, action, **kwargs):
        import asyncio
        try:
            return json.dumps(await asyncio.to_thread(inspect_skill, name, action), ensure_ascii=False)
        except (ValueError, OSError) as exc:
            return ToolResult.error(str(exc))
