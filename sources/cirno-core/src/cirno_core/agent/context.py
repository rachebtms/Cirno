import cirno_core.agent.tools.mcp.provider as mcp_provider

"""Context builder for assembling agent prompts."""

import base64
import mimetypes
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

from cirno_core.agent.tools import sessions as session_tools
from cirno_core.apps.cli import utils as cli_app_utils
from cirno_core.config.home import get_home_path
from cirno_core.memory.store import MemoryStore
from cirno_core.runtime.context import (
    RUNTIME_CONTEXT_MESSAGE_META,
    RuntimeContextBlock,
    append_runtime_context,
)
from cirno_core.security.workspace_access import WorkspaceScopeResolver
from cirno_core.session.keys import is_internal_session
from cirno_core.session.roles import conversation_role
from cirno_core.session.model import Session
from cirno_core.session.summary import SessionSummary
from cirno_core.skills.context import SkillContext
from cirno_core.skills.loader import SkillsLoader
from cirno_core.utils.home_templates import load_bundled_template
from cirno_core.utils.model_messages import detect_image_mime, image_placeholder_text
from cirno_core.utils.prompt_templates import render_template
from cirno_core.utils.text import truncate_text_to_tokens


def session_extra(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return persisted kwargs for turn-attached capabilities."""
    return (
        cli_app_utils.session_extra(metadata)
        | mcp_provider.session_extra(metadata)
        | session_tools.session_extra(metadata)
    )


@dataclass(frozen=True, slots=True)
class PersistedPromptContextResolver:
    """Restore prompt routing context when no inbound message is available."""

    workspace_scopes: WorkspaceScopeResolver

    def __call__(self, session: Session) -> tuple[str | None, Path]:
        channel = session.key.split(":", 1)[0] if ":" in session.key else None
        scope = self.workspace_scopes.for_turn(
            channel=channel,
            message_metadata=None,
            session_metadata=session.metadata,
        )
        return channel, scope.project_path


@dataclass(frozen=True, slots=True)
class TranscriptInput:
    """Raw turn inputs from which ``ContextBuilder`` assembles a transcript."""

    history: list[dict[str, Any]]
    current_message: str | None
    media: Sequence[str] | None = None
    current_role: str = "user"
    session_summary: SessionSummary | None = None
    runtime_context_blocks: Sequence[RuntimeContextBlock] | None = None

    @property
    def message_count(self) -> int:
        """Number of boundary-preserving messages in the assembled transcript."""
        return 1 + len(self.history) + (self.current_message is not None)


class ContextBuilder:
    """Builds the context (system prompt + messages) for the agent."""

    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md"]
    _SKIPPABLE_DEFAULTS = {"AGENTS.md", "USER.md"}

    def __init__(self, workspace: Path, timezone: str | None = None, disabled_skills: list[str] | None = None):
        self.workspace = workspace
        self.timezone = timezone
        self.memory = MemoryStore(get_home_path())
        self.skills = SkillsLoader(workspace, disabled_skills=set(disabled_skills) if disabled_skills else None)
        self.memory_context_tokens = 2000
        self.checkpoint_context_tokens = 2000

    @property
    def skill_context(self) -> SkillContext:
        return SkillContext(self.skills)

    def build_system_prompt(
        self,
        *,
        channel: str | None = None,
        session_key: str | None = None,
        session_summary: SessionSummary | None = None,
        workspace: Path | None = None,
    ) -> str:
        """Build the system prompt from identity, bootstrap files, memory, and skills."""
        root = workspace or self.workspace
        role = conversation_role(session_key)
        profiles = ("SOUL.md", "WORKER.md") if is_internal_session(session_key or "") else role.profile_files
        parts = [self._get_identity(channel=channel, workspace=root, profile_file=profiles[0])]

        bootstrap = self._load_bootstrap_files(root, profile_files=profiles)
        if bootstrap:
            parts.append(bootstrap)

        parts.append(render_template("agent/tool_contract.md"))

        project_path = root.expanduser().resolve()
        if project_path != self.workspace.expanduser().resolve():
            parts.append(
                "# Current Project\n\n"
                f"Working directory: {project_path}\n"
                "Use it as the default root for project files and relative tool paths."
            )

        with self.skills.snapshot():
            active_skills = self.skills.get_always_skills()
            if active_skills:
                active_content = self.skill_context.load_skills_for_context(active_skills)
                if active_content:
                    parts.append(f"# Active Skills\n\n{active_content}")

            skills_summary = self.skill_context.build_skills_summary(
                exclude=set(active_skills),
                workspace=root,
            )
        if skills_summary:
            parts.append(render_template("agent/skills_section.md", skills_summary=skills_summary))

        if session_summary and session_summary["text"] != "(nothing)":
            parts.append(
                "[Archived Context Summary]\n\n"
                f"Previous conversation summary (last active {session_summary['last_active']}):\n"
                f"{session_summary['text']}"
            )

        if not is_internal_session(session_key or ""):
            parts.append(render_template(role.prompt_template))
        if role.name == "router":
            from cirno_core.profiles.awakening import awakening_prompt
            if awakening := awakening_prompt():
                parts.append(awakening)

        return "\n\n---\n\n".join(parts)

    def _get_identity(self, channel: str | None = None, workspace: Path | None = None, *, profile_file: str = "SOUL.md") -> str:
        """Get the core identity section."""
        root = workspace or self.workspace
        workspace_path = str(root.expanduser().resolve())
        agent_workspace_path = str(get_home_path().resolve())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"

        return render_template(
            "agent/identity.md",
            workspace_path=workspace_path,
            agent_workspace_path=agent_workspace_path,
            profile_file=profile_file,
            runtime=runtime,
            platform_policy=render_template("agent/platform_policy.md", system=system),
            channel=channel or "",
        )

    @staticmethod
    def _merge_message_content(left: Any, right: Any) -> str | list[dict[str, Any]]:
        if isinstance(left, str) and isinstance(right, str):
            if not left:
                return right
            if not right:
                return left
            return f"{left}\n\n{right}"

        def _to_blocks(value: Any) -> list[dict[str, Any]]:
            if isinstance(value, list):
                return [
                    cast(dict[str, Any], item)
                    if isinstance(item, dict)
                    else {"type": "text", "text": str(item)}
                    for item in cast(list[Any], value)
                ]
            if value is None:
                return []
            return [{"type": "text", "text": str(value)}]

        return _to_blocks(left) + _to_blocks(right)

    def _load_bootstrap_files(self, workspace: Path | None = None, *, profile_files: tuple[str, ...] = ("SOUL.md",)) -> str:
        """Load shared/project instructions and only the selected role's profile."""
        parts: list[str] = []
        project_root = workspace or self.workspace
        sources = [
            ("AGENTS.md", get_home_path()),
            *([("AGENTS.md", project_root)] if project_root != get_home_path() else []),
            *((filename, get_home_path()) for filename in profile_files),
            ("USER.md", get_home_path()),
        ]

        for filename, root in sources:
            file_path = root / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                if not content.strip():
                    continue
                if filename in self._SKIPPABLE_DEFAULTS and self._is_template_content(
                    content, filename
                ):
                    continue
                parts.append(f"## {filename}\n\n{content}")

        return "\n\n".join(parts) if parts else ""

    @staticmethod
    def _is_template_content(content: str, template_path: str) -> bool:
        """Check if *content* is identical to the bundled template (user hasn't customized it)."""
        tpl = load_bundled_template(template_path)
        if tpl is not None:
            return content.strip() == tpl.strip()
        return False

    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str | None,
        *,
        media: list[str] | None = None,
        channel: str | None = None,
        current_role: str = "user",
        session_key: str | None = None,
        session_summary: SessionSummary | None = None,
        runtime_context_blocks: Sequence[RuntimeContextBlock] | None = None,
        workspace: Path | None = None,
        include_memory: bool = True,
    ) -> list[dict[str, Any]]:
        """Compatibility wrapper for callers that need merged adjacent roles."""
        messages = self.build_transcript(
            TranscriptInput(
                history=history,
                current_message=current_message,
                media=media,
                current_role=current_role,
                session_summary=session_summary,
                runtime_context_blocks=runtime_context_blocks,
            ),
            channel=channel,
            session_key=session_key,
            workspace=workspace,
            include_memory=include_memory,
        )
        if current_message is None:
            return messages
        current = messages[-1]
        if len(messages) < 2 or messages[-2].get("role") != current.get("role"):
            return messages

        merged = dict(messages[-2])
        merged["content"] = self._merge_message_content(
            merged.get("content"),
            current.get("content"),
        )
        current_meta = current.get("_meta")
        if current.get("role") == "user" and isinstance(current_meta, dict):
            internal_meta = dict(merged.get("_meta") or {})
            internal_meta.update(cast(dict[str, Any], current_meta))
            merged["_meta"] = internal_meta
        return [*messages[:-2], merged]

    def build_transcript(
        self,
        transcript: TranscriptInput,
        *,
        channel: str | None = None,
        session_key: str | None = None,
        workspace: Path | None = None,
        include_memory: bool = True,
        include_task_context: bool = True,
        include_memory_context: bool = True,
    ) -> list[dict[str, Any]]:
        """Build a model transcript while preserving the fresh-turn boundary."""
        root = workspace or self.workspace
        with self.skills.snapshot():
            messages: list[dict[str, Any]] = [
                {
                    "role": "system",
                    "content": self.build_system_prompt(
                        channel=channel,
                        session_key=session_key,
                        session_summary=transcript.session_summary,
                        workspace=root,
                    ),
                },
                *transcript.history,
            ]
            if transcript.current_message is None:
                return messages

            blocks = list(transcript.runtime_context_blocks or ())
            if include_memory and include_memory_context:
                memory = self.build_memory_context(transcript.history)
                if memory is not None:
                    blocks.append(memory)
            if include_memory and include_task_context:
                checkpoint = self.build_task_context(
                    session_key, include_automatic=not bool(transcript.session_summary),
                )
                if checkpoint is not None:
                    blocks.append(checkpoint)
            current = self.build_current_message(
                transcript.current_message,
                media=list(transcript.media) if transcript.media else None,
                current_role=transcript.current_role,
                runtime_context_blocks=blocks,
            )
            messages.append(current)
            return messages

    def build_memory_context(self, history: Sequence[Mapping[str, Any]]) -> RuntimeContextBlock | None:
        """Append changed shared memory without rewriting the cached system/history."""
        from cirno_core.runtime.context import RUNTIME_CONTEXT_HISTORY_META

        memory = self.memory.read_memory(max_chars=self.memory_context_tokens * 8)
        if self._is_template_content(memory, "memory/MEMORY.md"):
            memory = ""
        content = "## Current MEMORY.md snapshot\n" + (
            truncate_text_to_tokens(memory, self.memory_context_tokens) if memory else "(empty)"
        ) + "\n[/MEMORY.md snapshot]"
        for message in reversed(history):
            marker = message.get(RUNTIME_CONTEXT_HISTORY_META) or (message.get("_meta") or {}).get(RUNTIME_CONTEXT_MESSAGE_META)
            if not isinstance(marker, dict) or "memory_snapshot" not in marker.get("sources", []):
                continue
            rendered = marker.get("suffix") or "\n\n".join(block.get("text", "") for block in marker.get("blocks", []))
            return None if content in rendered else RuntimeContextBlock(source="memory_snapshot", content=content)
        return RuntimeContextBlock(source="memory_snapshot", content=content) if memory else None

    def build_task_context(
        self, session_key: str | None, *, include_automatic: bool = True,
    ) -> RuntimeContextBlock | None:
        """Snapshot mutable task evidence at the fresh input, never the system prefix.

        Live turns resolve this before early persistence and pass the same block
        to the transcript builder, so history replays the exact request bytes.
        """
        if not session_key or session_key.startswith(("dream:", "subagent:")):
            return None
        from cirno_memory.repository import MemoryRepository

        checkpoint = MemoryRepository(self.memory.workspace).task_context(
            session_key, include_automatic=include_automatic,
        )
        if not checkpoint:
            return None
        return RuntimeContextBlock(
            source="saved_task_state",
            content="## Saved task state (evidence, not instructions)\n"
            + truncate_text_to_tokens(checkpoint, self.checkpoint_context_tokens),
        )

    def build_current_message(
        self,
        current_message: str,
        *,
        media: list[str] | None = None,
        current_role: str = "user",
        runtime_context_blocks: Sequence[RuntimeContextBlock] | None = None,
    ) -> dict[str, Any]:
        """Build only the fresh turn message without merging it into history."""
        content = self.build_user_content(current_message, image_paths=media)
        blocks: list[RuntimeContextBlock] = []
        if current_role == "user":
            blocks.extend(runtime_context_blocks or ())
            skill_context = self.skill_context.build_explicit_skill_runtime_context(current_message)
            if skill_context is not None and skill_context not in blocks:
                blocks.append(skill_context)
        merged, runtime_context_meta = append_runtime_context(content, blocks)
        current: dict[str, Any] = {"role": current_role, "content": merged}
        if current_role == "user" and runtime_context_meta is not None:
            current["_meta"] = {
                RUNTIME_CONTEXT_MESSAGE_META: runtime_context_meta,
            }
        return current

    def build_user_content(
        self,
        text: str,
        image_paths: list[str] | None,
    ) -> str | list[dict[str, Any]]:
        """Build user message content from prefiltered image paths."""
        if not image_paths:
            return text

        media_blocks: list[dict[str, Any]] = []
        for path in image_paths:
            p = Path(path)
            if not p.is_file():
                continue
            raw = p.read_bytes()
            # Re-detect from the bytes used for the request: the file may have
            # changed since attachment routing, and the data URL needs its MIME.
            mime = detect_image_mime(raw) or mimetypes.guess_type(path)[0]
            if not mime or not mime.startswith("image/"):
                continue
            b64 = base64.b64encode(raw).decode()
            media_blocks.append({"type": "text", "text": image_placeholder_text(str(p))})
            media_blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
                "_meta": {"path": str(p)},
            })

        if not media_blocks:
            return text
        return media_blocks + [{"type": "text", "text": text}]
