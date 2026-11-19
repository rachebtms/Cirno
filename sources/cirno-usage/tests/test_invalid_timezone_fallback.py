"""All unrecognized timezone keys use the same UTC reporting fallback."""

from datetime import datetime, timezone

import pytest
from cirno_usage.store import LLMUsageStore


@pytest.mark.parametrize("name", ["/invalid/timezone", "../timezone", "a/../timezone"])
def test_invalid_timezone_key_falls_back_to_utc(tmp_path, name):
    store = LLMUsageStore(tmp_path / "usage.sqlite3")
    try:
        now = datetime(2026, 11, 18, tzinfo=timezone.utc)
        assert store.usage_payload(timezone_name=name, now=now) == store.usage_payload(timezone_name="UTC", now=now)
    finally:
        store.close()
