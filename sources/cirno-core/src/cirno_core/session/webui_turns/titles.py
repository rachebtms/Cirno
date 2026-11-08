"""Titles ownership for WebUI session presentation."""

from __future__ import annotations

import re
from typing import Any

from cirno_usage.context import llm_usage_source
from loguru import logger

from cirno_core.providers.base import LLMProvider
from cirno_core.runtime.context import public_history_message
from cirno_core.session.history_visibility import is_hidden_history_message
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.manager import SessionManager
from cirno_core.session.model import Session
from cirno_core.session.sqlite_store import SessionConflictError
from cirno_core.utils.reasoning import strip_think
from cirno_core.utils.text import truncate_text

from .contracts import WEBUI_SESSION_METADATA_KEY

WEBUI_TITLE_METADATA_KEY = "title"


WEBUI_TITLE_USER_EDITED_METADATA_KEY = "title_user_edited"


TITLE_MAX_CHARS = 60


TITLE_GENERATION_MAX_TOKENS = 96


def clean_generated_title(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    text = re.sub(r"^\s*(title|标题)\s*[:：]\s*", "", text, flags=re.IGNORECASE)
    text = text.strip().strip("\"'`“”‘’")
    text = strip_think(text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.rstrip("。.!！?？,，;；:")
    if len(text) > TITLE_MAX_CHARS:
        text = text[: TITLE_MAX_CHARS - 1].rstrip() + "…"
    return text


def _title_inputs(session: Session) -> tuple[str, str]:
    user_text = ""
    assistant_text = ""
    for message in session.messages:
        if message.get("_command") is True:
            continue
        if is_hidden_history_message(message):
            continue
        message = public_history_message(message)
        role = message.get("role")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        content = strip_think(content)
        if not content:
            continue
        if role == "user" and not user_text:
            user_text = content.strip()
        elif role == "assistant" and not assistant_text:
            assistant_text = content.strip()
        if user_text and assistant_text:
            break
    return user_text, assistant_text


def _latest_title_inputs(session: Session) -> tuple[str, str]:
    """Latest user/assistant texts, for turns executed on a shared session."""
    user_text = ""
    assistant_text = ""
    for message in reversed(session.messages):
        if message.get("_command") is True:
            continue
        if is_hidden_history_message(message):
            continue
        message = public_history_message(message)
        role = message.get("role")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        content = strip_think(content)
        if not content:
            continue
        if role == "user" and not user_text:
            user_text = content.strip()
        elif role == "assistant" and not assistant_text:
            assistant_text = content.strip()
        if user_text and assistant_text:
            break
    return user_text, assistant_text


async def maybe_generate_webui_title(
    *,
    sessions: SessionManager,
    session_key: str,
    provider: LLMProvider,
    model: str,
    target_session_key: str | None = None,
) -> bool:
    """Generate and persist a short title for WebUI-owned sessions.

    ``session_key`` owns the conversation content. Under unified-session
    routing this is the shared session while WebUI renders per-chat sessions,
    so pass ``target_session_key`` to project the title onto that per-chat
    session instead of storing it on the shared one.
    """
    if (target_session_key or session_key) == ROUTER_SESSION_KEY:
        return False
    routed_session = await sessions.state.read(session_key)
    if routed_session is None:
        return False
    target_is_routed = target_session_key is None or target_session_key == session_key
    if target_is_routed or target_session_key is None:
        target_session = routed_session
    else:
        target_session = await sessions.state.get(target_session_key)
    if (
        routed_session.metadata.get(WEBUI_SESSION_METADATA_KEY) is not True
        and target_session.metadata.get(WEBUI_SESSION_METADATA_KEY) is not True
    ):
        return False
    if target_session.metadata.get(WEBUI_TITLE_USER_EDITED_METADATA_KEY) is True:
        return False
    current_title = target_session.metadata.get(WEBUI_TITLE_METADATA_KEY)
    if isinstance(current_title, str) and current_title.strip():
        cleaned_current_title = clean_generated_title(current_title)
        if cleaned_current_title:
            if cleaned_current_title != current_title:

                def clean_title(metadata: dict[str, Any]) -> None:
                    if (
                        metadata.get(WEBUI_TITLE_METADATA_KEY) == current_title
                        and metadata.get(WEBUI_TITLE_USER_EDITED_METADATA_KEY) is not True
                    ):
                        metadata[WEBUI_TITLE_METADATA_KEY] = cleaned_current_title

                await sessions.state.mutate_metadata(
                    target_session.key,
                    clean_title,
                    expected_generation=target_session.generation,
                )
            return False
        target_session.metadata.pop(WEBUI_TITLE_METADATA_KEY, None)

    if target_is_routed:
        user_text, assistant_text = _title_inputs(routed_session)
    else:
        # Shared-session content mixes every channel; generation runs right
        # after this turn, so its exchange is the latest pair.
        user_text, assistant_text = _latest_title_inputs(routed_session)
    if not user_text:
        return False

    prompt = (
        "Generate a concise title for this chat.\n"
        "Rules:\n"
        "- Use the same language as the user when practical.\n"
        "- 3 to 8 words.\n"
        "- No quotes.\n"
        "- No punctuation at the end.\n"
        "- Return only the title.\n\n"
        f"User: {truncate_text(user_text, 1_000)}"
    )
    if assistant_text:
        prompt += f"\nAssistant: {truncate_text(assistant_text, 1_000)}"

    try:
        with (
            llm_usage_source("system"),
            logger.contextualize(purpose="webui_title", session_key=target_session.key),
        ):
            response = await provider.chat_stream_with_retry(
                [
                    {
                        "role": "system",
                        "content": (
                            "You write short, neutral chat titles. Return only the title text."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                tools=None,
                model=model,
                max_tokens=TITLE_GENERATION_MAX_TOKENS,
                temperature=0.2,
                reasoning_effort=None,
                retry_mode="standard",
            )
    except Exception:
        logger.opt(exception=True).debug(
            "Failed to generate webui session title for {}", session_key
        )
        return False

    title = clean_generated_title(response.content)
    if not title or title.lower().startswith("error"):
        logger.debug(
            "WebUI title generation returned no usable title for {} (finish_reason={})",
            session_key,
            response.finish_reason,
        )
        return False

    def set_title(metadata: dict[str, Any]) -> bool:
        if metadata.get(WEBUI_TITLE_USER_EDITED_METADATA_KEY) is True:
            return False
        if metadata.get(WEBUI_TITLE_METADATA_KEY) != current_title:
            return False
        metadata[WEBUI_TITLE_METADATA_KEY] = title
        return True

    try:
        changed, _ = await sessions.state.mutate_metadata(
            target_session.key,
            set_title,
            expected_generation=target_session.generation,
        )
    except SessionConflictError:
        return False
    return changed


async def maybe_generate_webui_title_after_turn(
    *,
    channel: str,
    chat_id: str,
    metadata: dict[str, Any],
    sessions: SessionManager,
    session_key: str,
    provider: LLMProvider,
    model: str,
) -> bool:
    if channel != "websocket" or metadata.get(WEBUI_SESSION_METADATA_KEY) is not True:
        return False
    origin_session_key = f"{channel}:{chat_id}"
    return await maybe_generate_webui_title(
        sessions=sessions,
        session_key=session_key,
        provider=provider,
        model=model,
        target_session_key=(origin_session_key if origin_session_key != session_key else None),
    )
