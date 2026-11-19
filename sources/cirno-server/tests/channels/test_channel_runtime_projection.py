"""Desired configuration must not conceal a live adapter after a failed stop."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.bus.queue import MessageBus
from cirno_core.config.schema import Config
from cirno_server.channels.runtimes import ChannelRuntimes
from cirno_server.features.service import with_channel_runtime_status


def payload(enabled):
    return {"features": [{
        "name": "fixture", "type": "channel", "enabled": enabled,
        "ready": False, "instances": [{"id": "worker", "enabled": enabled, "configured": True}],
    }], "enabled_count": int(enabled)}


@pytest.mark.parametrize("desired,state,running,expected", [
    (False, "running", True, "running"),
    (False, "starting", False, "starting"),
    (False, "failed", True, "failed"),
    (False, "failed", False, "stopped"),
    (True, "failed", True, "failed"),
    (True, "failed", False, "failed"),
    (True, "running", True, "running"),
])
def test_desired_flag_and_actual_running_are_independent(desired, state, running, expected):
    original = payload(desired)
    snapshot = deepcopy(original)
    runtime = {"fixture.worker": {
        "owner": "fixture", "instance_id": "worker", "state": state, "running": running,
        **({"error": "Replacement failed"} if state == "failed" else {}),
    }}
    decorated = with_channel_runtime_status(original, runtime)
    feature = decorated["features"][0]
    assert feature["enabled"] is desired
    assert feature["runtime_status"] == expected
    assert feature["running"] is running
    assert feature["instances"][0]["running"] is running
    assert feature["instances"][0]["runtime_status"] == expected
    assert decorated["enabled_count"] == int(running)
    assert feature["ready"] is (expected == "running")
    assert original == snapshot


def test_partially_failed_channel_preserves_active_instances_and_count():
    source = payload(True)
    source["features"][0]["instances"].append({"id": "other", "enabled": True, "configured": True})
    statuses = {
        "fixture.worker": {"owner": "fixture", "instance_id": "worker", "state": "running", "running": True},
        "fixture.other": {"owner": "fixture", "instance_id": "other", "state": "failed", "running": False, "error": "Start failed"},
    }
    feature = with_channel_runtime_status(source, statuses)["features"][0]
    assert feature["runtime_status"] == "failed"
    assert feature["running"] is True
    assert feature["ready"] is False
    assert feature["runtime_error"] == "Start failed"


async def test_failed_stop_keeps_adapter_visible_for_a_second_stop_attempt():
    runtimes = ChannelRuntimes(Config(), MessageBus(), AsyncMock())
    channel = SimpleNamespace(is_running=True, stop=AsyncMock(side_effect=RuntimeError("Stop failed")))
    runtimes.channels["fixture.worker"] = channel
    runtimes.owners["fixture.worker"] = "fixture"
    runtimes.specs["fixture.worker"] = ("fixture", "worker")
    with pytest.raises(RuntimeError, match="Stop failed"):
        await runtimes.stop("fixture.worker")
    feature = with_channel_runtime_status(payload(False), runtimes.status())["features"][0]
    assert feature["runtime_status"] == "running"
    assert feature["running"] is True
    channel.stop.side_effect = None
    await runtimes.stop("fixture.worker")
    assert channel.stop.await_count == 2


def test_reprojecting_a_recovered_runtime_clears_only_stale_runtime_errors():
    failed = {"fixture.worker": {
        "owner": "fixture", "instance_id": "worker", "state": "failed", "running": False,
        "error": "Old failure",
    }}
    previous = with_channel_runtime_status(payload(True), failed)
    healthy = {"fixture.worker": {
        "owner": "fixture", "instance_id": "worker", "state": "running", "running": True,
    }}
    current = with_channel_runtime_status(previous, healthy)["features"][0]
    assert "runtime_error" not in current
    assert "runtime_error" not in current["instances"][0]
    assert previous["features"][0]["runtime_error"] == "Old failure"
