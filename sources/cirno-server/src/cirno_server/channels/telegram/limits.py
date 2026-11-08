"""Telegram message and draft size limits."""

TELEGRAM_MAX_MESSAGE_LEN = 4000  # Telegram message character limit
# Telegram's actual API limit is 4096; we split raw markdown at 4000 as a
# safety margin for mid-stream edits (plain text).  On stream end, we split
# raw markdown into chunks whose rendered HTML fits Telegram's true 4096-char
# boundary so the final rendered message never overflows.
TELEGRAM_HTML_MAX_LEN = 4096
# Bot API rich messages accept up to 32,768 UTF-8 characters. Raw Markdown is
# counted conservatively here; Python's str length counts Unicode code points,
# so multibyte text must not be split at an encoded-byte boundary.
TELEGRAM_RICH_MAX_LEN = 32768
TELEGRAM_REPLY_CONTEXT_MAX_LEN = TELEGRAM_MAX_MESSAGE_LEN  # Max length for reply context in user message
TELEGRAM_RICH_DRAFT_MIN_INTERVAL = 0.75  # 40 draft updates per 30 seconds per chat
# Bound for in-flight compaction notices in case a terminal phase never arrives.
COMPACTION_NOTICES_MAX = 64
