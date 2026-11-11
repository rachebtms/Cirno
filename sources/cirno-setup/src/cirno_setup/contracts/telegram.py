"""Telegram requirements, shared by channel management and setup."""

REQUIREMENTS = (
    "python-telegram-bot[socks,webhooks]>=22.6,<23.0",
    "socksio>=1.0.0,<2.0.0",
    "python-socks[asyncio]>=2.8.0,<3.0.0; sys_platform != 'win32'",
)
