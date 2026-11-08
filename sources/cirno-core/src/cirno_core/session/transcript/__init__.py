"""Public conversation recording, replay and navigation API."""

from .activity import tool_trace_lines_from_events
from .contracts import (
    MAX_SESSION_MENTIONS,
    WEBUI_FORK_MARKER_EVENT,
    WEBUI_TRANSCRIPT_INCOMPLETE_KEY,
    WEBUI_TRANSCRIPT_SCHEMA_VERSION,
    TranscriptReplayStats,
)
from .identities import webui_transcript_revision
from .inputs import build_user_transcript_event, session_display_facts
from .media import rewrite_local_markdown_images
from .paging import decode_transcript_cursor, read_transcript_lines
from .prompt_directory import PromptPage, PromptPageRequest, prompt_directory_page
from .prompts import (
    PromptSummary,
    prompt_index_revision,
)
from .recorder import (
    WebUITranscriptRecorder,
    append_session_message_input,
    append_transcript_object,
)
from .records import (
    normalize_session_mentions_metadata,
    normalize_session_message_ui_metadata,
    normalize_webui_turn_id,
    webui_message_source,
)
from .status import completed_turn_ids, has_pending_tool_calls, has_unfinished_transcript_tail
from .thread import build_session_thread_response, build_webui_thread_response
from .traces import build_webui_trace_detail_response

__all__ = [
    "MAX_SESSION_MENTIONS",
    "PromptPage",
    "PromptPageRequest",
    "PromptSummary",
    "TranscriptReplayStats",
    "WEBUI_FORK_MARKER_EVENT",
    "WEBUI_TRANSCRIPT_INCOMPLETE_KEY",
    "WEBUI_TRANSCRIPT_SCHEMA_VERSION",
    "WebUITranscriptRecorder",
    "append_session_message_input",
    "append_transcript_object",
    "build_session_thread_response",
    "build_user_transcript_event",
    "build_webui_thread_response",
    "build_webui_trace_detail_response",
    "completed_turn_ids",
    "decode_transcript_cursor",
    "has_pending_tool_calls",
    "has_unfinished_transcript_tail",
    "normalize_session_mentions_metadata",
    "normalize_session_message_ui_metadata",
    "normalize_webui_turn_id",
    "prompt_directory_page",
    "prompt_index_revision",
    "read_transcript_lines",
    "rewrite_local_markdown_images",
    "session_display_facts",
    "tool_trace_lines_from_events",
    "webui_message_source",
    "webui_transcript_revision",
]
