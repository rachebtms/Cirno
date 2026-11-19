"""Feature toggles keep raw config fields and never expose a partial JSON file."""

import builtins
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest
from cirno_core.utils.file_transactions import file_write_transaction
from cirno_server.features import service


def test_feature_config_write_failure_preserves_previous_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text('{"channels":{"telegram":{"enabled":false}},"owner_field":"keep"}', encoding="utf-8")
    before = path.read_bytes()
    real_open = builtins.open

    class FailedWriter:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def write(self, data):
            self.stream.write(data[:max(1, len(data) // 2)])
            raise OSError("disk write failed")

    def failing_open(target, mode="r", *args, **kwargs):
        stream = real_open(target, mode, *args, **kwargs)
        if mode in {"w", "xb"} and Path(target).parent == tmp_path:
            return FailedWriter(stream)
        return stream

    monkeypatch.setattr(builtins, "open", failing_open)
    with pytest.raises(OSError, match="disk write failed"):
        service.write_config_data(path, {"channels": {"telegram": {"enabled": True}}})
    assert path.read_bytes() == before
    assert not list(tmp_path.glob(".config.json.*.tmp"))


def test_concurrent_feature_toggles_preserve_both_changes(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text('{"channels":{},"owner_field":"keep"}', encoding="utf-8")
    first_read, second_seen = threading.Event(), threading.Event()
    read = service.read_config_data

    def paused_read(target):
        data = read(target)
        if threading.current_thread().name.startswith("feature-first"):
            first_read.set()
            assert second_seen.wait(3)
        return data

    @contextmanager
    def observed_transaction(paths):
        if threading.current_thread().name.startswith("feature-second"):
            second_seen.set()
        with file_write_transaction(paths):
            yield

    def second_toggle():
        service.set_channel_config_enabled(path, "email", None, True, instance_id=None)
        second_seen.set()

    monkeypatch.setattr(service, "read_config_data", paused_read)
    monkeypatch.setattr(service, "file_write_transaction", observed_transaction, raising=False)
    with ThreadPoolExecutor(1, thread_name_prefix="feature-first") as first, ThreadPoolExecutor(1, thread_name_prefix="feature-second") as second:
        pending = first.submit(service.set_channel_config_enabled, path, "telegram", None, True, instance_id=None)
        assert first_read.wait(2)
        other = second.submit(second_toggle)
        pending.result(3)
        other.result(3)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["channels"] == {"telegram": {"enabled": True}, "email": {"enabled": True}}
    assert saved["owner_field"] == "keep"
