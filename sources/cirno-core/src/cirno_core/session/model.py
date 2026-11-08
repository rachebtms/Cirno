"""Conversation records, runtime privacy policy and model replay projection."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast
from uuid import uuid4

from cirno_core.providers.contracts import ProviderConversationState
from cirno_core.runtime.context import RUNTIME_CONTEXT_HISTORY_META, public_history_message
from cirno_core.session.history_visibility import HIDDEN_HISTORY_META
from cirno_core.session.summary import SUMMARY_CONTINUATION_TEXT, is_summary_checkpoint
from cirno_core.utils.model_messages import content_with_media_breadcrumbs, find_legal_message_start, recent_message_start_index
from cirno_core.utils.token_estimation import estimate_message_tokens

@dataclass(frozen=True)
class SessionPolicy:
    """Runtime rules that do not belong in durable session data."""

    persist: bool = True
    log_content: bool = True
    disabled_tools: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SessionIdentity:
    """Cached generation and immutable runtime policy for one session."""

    generation: str
    policy: SessionPolicy


@dataclass
class Session:
    """Message history, runtime state, and metadata for one agent session."""

    key: str  # namespace:identity
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    # Archive cursor for messages already summarized by memory consolidation.
    last_archived: int = 0
    provider_state: ProviderConversationState | None = field(default=None, repr=False)
    policy: SessionPolicy = field(default_factory=SessionPolicy, repr=False, compare=False)

    # Owner-private committed snapshot. Never mutate or expose its records as draft data.
    _baseline: Session | None = field(default=None, repr=False, compare=False)
    # Explicit draft command, committed with history against the latest owner journal.
    consumed_followup_ids: frozenset[str] = field(default_factory=frozenset, repr=False, compare=False)
    persisted: bool = field(default=False, repr=False, compare=False)
    revision: int = field(default=0, repr=False, compare=False)
    generation: str = field(default_factory=lambda: uuid4().hex, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.metadata), dict):
            self.metadata = {}
        if not isinstance(cast(object, self.provider_state), ProviderConversationState):
            self.provider_state = None
        # An out-of-range offset (corrupt metadata) would hide all history; reset it.
        last_archived = cast(object, self.last_archived)
        if (
            isinstance(last_archived, bool)
            or not isinstance(last_archived, int)
            or not 0 <= last_archived <= len(self.messages)
        ):
            self.last_archived = 0


    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """Add a message to the session."""
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        self.messages.append(msg)
        self.updated_at = datetime.now()

    def commit_summary_checkpoint(
        self,
        summary: str,
        *,
        insert_at: int | None = None,
        last_active: datetime | None = None,
    ) -> None:
        """Replace replay before a hidden boundary while preserving the transcript."""
        boundary = len(self.messages) if insert_at is None else insert_at
        self.messages.insert(boundary, {
            "role": "user",
            "content": SUMMARY_CONTINUATION_TEXT,
            HIDDEN_HISTORY_META: True,
            "timestamp": datetime.now().isoformat(),
        })
        self.metadata["_last_summary"] = {
            "text": summary,
            "last_active": (last_active or self.updated_at).isoformat(),
        }
        self.last_archived = boundary

    def get_history(
        self,
        max_messages: int = 0,
        *,
        max_tokens: int = 0,
        extend_to_user: bool = False,
        include_runtime_context: bool = True,
    ) -> list[dict[str, Any]]:
        """Return recent replayable messages for LLM input.

        A committed summary checkpoint replaces its old prefix with the stored
        summary and resumes replay after its hidden boundary marker. The marker
        is not a user request and must not resume an old task on the next turn.
        A positive ``max_messages`` applies an additional caller-owned count limit.
        """
        replayable = self.messages[self.last_archived:]
        if max_messages <= 0:
            start_idx = 0
        else:
            start_idx = recent_message_start_index(
                replayable,
                max_messages,
                extend_to_user=extend_to_user,
            )
        sliced = replayable[start_idx:]

        # Avoid starting mid-turn when possible, except for proactive
        # assistant deliveries that the user may be replying to.
        for i, message in enumerate(sliced):
            if message.get("role") == "user":
                start = i
                if i > 0 and sliced[i - 1].get("_channel_delivery"):
                    start = i - 1
                sliced = sliced[start:]
                break

        # Drop orphan tool results at the front.
        start = find_legal_message_start(sliced)
        if start:
            sliced = sliced[start:]

        out: list[dict[str, Any]] = []
        for message in sliced:
            if message.get("_command") or is_summary_checkpoint(message):
                continue
            has_persisted_runtime_context = isinstance(
                message.get(RUNTIME_CONTEXT_HISTORY_META),
                dict,
            )
            if not include_runtime_context:
                message = public_history_message(message)
            content = message.get("content", "")
            role = message.get("role")
            # Synthesize an ``[image: path]`` breadcrumb from the persisted
            # ``media`` kwarg so LLM replay still sees *something* where the
            # image used to be. Without this, an image-only user turn
            # replays as an empty user message — the assistant's reply then
            # looks like it's responding to nothing.
            content = content_with_media_breadcrumbs(
                role,
                content,
                message.get("media"),
            )
            cli_apps = cast(object, message.get("cli_apps"))
            if (
                include_runtime_context
                and not has_persisted_runtime_context
                and role == "user"
                and isinstance(cli_apps, list)
                and cli_apps
                and isinstance(content, str)
            ):
                cli_lines: list[str] = []
                for item in cast(list[object], cli_apps[:8]):
                    if not isinstance(item, dict):
                        continue
                    item_data = cast(dict[object, object], item)
                    name = str(item_data.get("name") or "").strip().lower()
                    if not name:
                        continue
                    entry_point = (
                        str(item_data.get("entry_point") or "unknown").strip() or "unknown"
                    )
                    cli_lines.append(
                        f"[CLI App Attachment: @{name}; tool=run_cli_app; entry_point={entry_point}; "
                        f"skill=skills/cli-app-{name}/SKILL.md]"
                    )
                if cli_lines:
                    breadcrumbs = "\n".join(cli_lines)
                    content = f"{content}\n{breadcrumbs}" if content else breadcrumbs
            if role == "assistant" and isinstance(content, str) and not content.strip():
                if not any(key in message for key in ("tool_calls", "reasoning_content", "thinking_blocks")):
                    continue
            entry: dict[str, Any] = {"role": message["role"], "content": content}
            for key in ("tool_calls", "tool_call_id", "name", "reasoning_content", "thinking_blocks"):
                if key in message:
                    entry[key] = message[key]
            out.append(entry)

        if max_tokens > 0 and out:
            kept: list[dict[str, Any]] = []
            used = 0
            for message in reversed(out):
                tokens = estimate_message_tokens(message)
                if kept and used + tokens > max_tokens:
                    break
                kept.append(message)
                used += tokens
            kept.reverse()

            # Keep history aligned to the first visible user turn.
            first_user = next((i for i, m in enumerate(kept) if m.get("role") == "user"), None)
            if first_user is not None:
                kept = kept[first_user:]
            else:
                # Tight token budgets can otherwise leave assistant-only tails.
                # If a user turn exists in the unsliced output, recover the
                # nearest one even if it slightly exceeds the token budget.
                recovered_user = next(
                    (i for i in range(len(out) - 1, -1, -1) if out[i].get("role") == "user"),
                    None,
                )
                if recovered_user is not None:
                    kept = out[recovered_user:]

            # And keep a legal tool-call boundary at the front.
            start = find_legal_message_start(kept)
            if start:
                kept = kept[start:]
            out = kept
        return out

    def clear(self) -> None:
        """Clear all messages and reset session to initial state."""
        self.messages = []
        self.last_archived = 0
        self.provider_state = None
        self.updated_at = datetime.now()
        self.metadata.pop("_last_summary", None)
        self.metadata.pop("_stopped_at_iteration_limit", None)
