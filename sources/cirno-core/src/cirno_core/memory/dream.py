"""Dream batch ownership, tools, confirmations, and durable edit reports."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from loguru import logger

from cirno_core.utils.prompt_templates import render_template
from cirno_core.utils.workspace_prompts import (
    WORKSPACE_PROMPT_MAX_CHARS,
    has_workspace_prompt_override,
    load_workspace_prompt_override,
    workspace_prompt_file,
)

if TYPE_CHECKING:
    from cirno_core.agent.tools.registry import ToolRegistry
    from cirno_core.memory.store import MemoryStore


class DreamMemory:
    _DREAM_CONTENT_PATHS = ("SOUL.md", "WORKER.md", "USER.md", "memory/MEMORY.md")

    def __init__(self, store: MemoryStore):
        self.store = store
        self.run_lock = asyncio.Lock()
        self._dream_prompt_oversize_logged = False
        self.batch_token: str | None = None
        self._dream_owner: dict[str, Any] | None = None
        self._dream_evidence_ids: set[str] | None = None
        self._dream_shared_profiles = True
        self._dream_revision_baseline = 0

    @property
    def prompt_file(self) -> Path:
        return workspace_prompt_file(self.store.workspace, "dream")

    def has_prompt_override(self) -> bool:
        return has_workspace_prompt_override(self.prompt_file)

    @staticmethod
    def default_prompt() -> str:
        from cirno_core.skills.metadata import BUILTIN_SKILLS_DIR

        return render_template(
            "agent/dream.md",
            strip=True,
            skill_creator_path=str(BUILTIN_SKILLS_DIR / "skill-creator" / "SKILL.md"),
        )

    def _template(self) -> str:
        text, original_chars = load_workspace_prompt_override(self.prompt_file)
        if text is not None:
            if (
                original_chars > WORKSPACE_PROMPT_MAX_CHARS
                and not self._dream_prompt_oversize_logged
            ):
                self._dream_prompt_oversize_logged = True
                logger.warning(
                    "workspace Dream prompt exceeds {} chars ({}); truncating. "
                    "Further occurrences suppressed.",
                    WORKSPACE_PROMPT_MAX_CHARS,
                    original_chars,
                )
            return text
        return self.default_prompt()

    def build_prompt(self, *, max_entries: int = 20) -> tuple[str, int] | None:
        """Build the Dream prompt with unprocessed history context.

        Returns ``(prompt, last_cursor)`` or ``None`` if nothing to process.

        The current contents of the durable memory files (SOUL.md, USER.md,
        memory/MEMORY.md) reach Dream through the normal agent system context.
        """
        from cirno_memory.repository import MemoryRepository

        from cirno_core.config.loader import load_config

        repo = MemoryRepository(self.store.workspace)
        # Re-ingestion is idempotent and repairs a journal append interrupted before indexing.
        imported_cursor = self.store.journal.get_last_dream_cursor()
        for entry, cursor in self.store.journal.iter_valid_entries():
            if cursor <= imported_cursor:
                continue
            repo.ingest_history(
                entry["cursor"],
                entry["content"],
                entry.get("session_key"),
                entry.get("source_refs"),
                timestamp=entry.get("timestamp"),
            )
        config = load_config().agents.defaults.dream
        batch = repo.pending(
            limit=min(max_entries, config.batch_entries), max_chars=config.batch_chars
        )
        if batch is None:
            return None
        self.batch_token, records = batch
        self._dream_owner = dict(
            session_key=records[0].get("session_key"),
            project_id=records[0].get("project_id"),
            maintenance=False,
        )
        if records[0]["scope"] == "user":
            self._dream_owner = dict(session_key="dream:shared", project_id=None, maintenance=False)
        self._dream_evidence_ids = {record["id"] for record in records}
        self._dream_shared_profiles = records[0]["scope"] == "user"
        with repo.connect() as db:
            self._dream_revision_baseline = db.execute(
                "SELECT coalesce(max(rowid),0) FROM revisions"
            ).fetchone()[0]
        history_text = "\n\n".join(
            f"[Memory ID: {record['id']}; revision: {record['revision']}; scope: {record['scope']}; source: {record['source']}]\n{record['content']}"
            for record in records
        )
        template = self._template()
        prompt = (
            f"{template}\n\n## Required per-input confirmation\n"
            "For EVERY Memory ID below, call memory__confirm(memory_id=..., input_revision=..., "
            "outcome=created|merged|skipped|failed, target_ids=[...], reason=...). "
            "created/merged must reference persisted knowledge grounded in that input (based_on or supports link). "
            "Use skipped with a specific reason when nothing durable is needed; failed for unresolved work. "
            "Unconfirmed/failed inputs stay queued even when you finish normally. Confirm unchanged input revisions only.\n\n"
            f"## Conversation History\n{history_text}"
        )
        history_cursors = [
            int(record["id"].split("-", 2)[1])
            for record in records
            if record["id"].startswith("history-") and record["id"].split("-", 2)[1].isdigit()
        ]
        return (prompt, max([self.store.journal.get_last_dream_cursor(), *history_cursors]))

    def finish_batch(
        self, token: str | None = None, *, error: str | None = None, preempted: bool = False
    ) -> dict[str, int | bool] | None:
        from cirno_memory.repository import MemoryRepository

        if token:
            result = cast(
                dict[str, int | bool],
                MemoryRepository(self.store.workspace).finish(
                    token, error=error, preempted=preempted
                ),
            )
            self.batch_token = None
            if not preempted:
                import sqlite3

                from cirno_core.notifications.inbox import NotificationInbox

                try:
                    NotificationInbox().record(
                        "dream:" + token,
                        "system",
                        "dream",
                        status="failed"
                        if error
                        else "partial"
                        if (result or {}).get("retained")
                        else "succeeded",
                        body=error or "",
                        data=result or {},
                    )
                except (OSError, ValueError, sqlite3.Error):
                    logger.exception("Could not record Dream notification")
            return result

    def content_diff(self) -> str:
        """Structured summary of uncommitted changes to the durable memory files.

        Returns "" when git is unavailable or no content file changed. This is
        the ground-truth input for diff-grounded Dream commit messages.
        """
        from cirno_memory.repository import MemoryRepository

        with MemoryRepository(self.store.workspace).connect() as db:
            changed = db.execute(
                "SELECT memory_id,revision FROM revisions WHERE rowid>? LIMIT 50",
                (self._dream_revision_baseline,),
            ).fetchall()
        records = "\n".join(f"Memory {row[0]} revision {row[1]} saved" for row in changed)
        files = (
            self.store.git.summarize_working_tree(list(self._DREAM_CONTENT_PATHS))
            if self.store.git.is_initialized()
            else ""
        )
        return "\n".join(part for part in (files, records) if part)

    def build_tools(self) -> ToolRegistry:
        """Build the restricted tool registry used by Dream runs."""
        from cirno_core.agent.tools.apply_patch import ApplyPatchTool
        from cirno_core.agent.tools.file_state import FileStates
        from cirno_core.agent.tools.filesystem import EditFileTool, ReadFileTool, WriteFileTool
        from cirno_core.agent.tools.registry import ToolRegistry
        from cirno_core.skills.metadata import BUILTIN_DOCUMENTS_DIR, BUILTIN_SKILLS_DIR

        tools = ToolRegistry()
        from cirno_core.agent.tools.instance_features import InspectSkillTool, MemoryTool

        tools.register(InspectSkillTool())
        tools.register(
            MemoryTool(
                maintenance=True,
                owner_access=self._dream_owner,
                evidence_ids=self._dream_evidence_ids,
                batch_token=self.batch_token,
            )
        )
        file_states = FileStates()
        workspace = self.store.workspace
        skills_dir = workspace / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        extra_read = [
            path for path in (BUILTIN_SKILLS_DIR, BUILTIN_DOCUMENTS_DIR) if path.exists()
        ] + [workspace / "skills-history"]
        readable_files = [self.store.memory_file, self.store.soul_file, self.store.worker_file, self.store.user_file]
        editable_files = readable_files if self._dream_shared_profiles else []

        tools.register(
            ReadFileTool(
                workspace=workspace,
                allowed_dir=skills_dir,
                extra_read_allowed_dirs=extra_read,
                extra_read_allowed_files=readable_files,
                file_states=file_states,
            )
        )
        tools.register(
            EditFileTool(
                workspace=workspace,
                allowed_dir=skills_dir,
                extra_write_allowed_files=editable_files,
                file_states=file_states,
            )
        )
        tools.register(
            ApplyPatchTool(
                workspace=workspace,
                allowed_dir=skills_dir,
                extra_write_allowed_files=editable_files,
                file_states=file_states,
            )
        )
        tools.register(
            WriteFileTool(
                workspace=workspace,
                allowed_dir=skills_dir,
                extra_write_allowed_files=editable_files,
                file_states=file_states,
            )
        )
        return tools

    @staticmethod
    def run_completed(
        resp: object | None,
    ) -> bool:
        """Return True when the Dream agent reached a normal terminal response."""
        metadata = getattr(resp, "metadata", None)
        if not isinstance(metadata, dict):
            return False
        return cast(dict[str, Any], metadata).get("_stop_reason") == "completed"

    @staticmethod
    def incompletion_reason(
        resp: object | None,
    ) -> str:
        """Human-readable explanation of why a Dream run cannot advance."""
        metadata = getattr(resp, "metadata", None)
        if isinstance(metadata, dict):
            stop_reason = cast(dict[str, Any], metadata).get("_stop_reason", "unknown")
        else:
            stop_reason = "missing response metadata"
        return f"stop_reason: {stop_reason}"

    @staticmethod
    def session_key() -> str:
        """Identify concurrent or immediately consecutive Dream runs independently."""
        return f"dream:{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:12]}"

    @staticmethod
    def commit_message(prefix: str, diff_body: str) -> str:
        """Build a Dream commit message grounded in the real working-tree diff.

        *diff_body* is a structured, machine-derived summary of the actual file
        changes (see :meth:`content_diff` /
        :meth:`GitStore.summarize_working_tree`). The LLM narrative is
        deliberately excluded so the audit record (``/dream-log``) reflects the
        filesystem's truth, not the model's self-report.

        An empty *diff_body* yields the bare *prefix*, which ``auto_commit``
        turns into a no-op when there is nothing to stage.
        """
        diff_body = (diff_body or "").strip()
        if not diff_body:
            return prefix
        return f"{prefix}\n\n{diff_body}"
