"""A pathological line must not hold a search worker or the event loop forever."""

import subprocess
import sys

import pytest


@pytest.mark.parametrize("mode", ["content", "count", "files_with_matches"])
def test_pathological_regex_obeys_scan_deadline_and_yields_to_other_tasks(tmp_path, mode):
    (tmp_path / "source.txt").write_text("a" * 5000 + "!")
    # Keep the regression outside pytest's process: the old re engine holds the
    # GIL, defeating both asyncio.wait_for and the worker's cooperative budget.
    script = """
import asyncio, sys
from pathlib import Path
from cirno_core.agent.tools.search import GrepTool
from cirno_core.agent.tools.registry import is_tool_error_result

async def main():
    tool = GrepTool(workspace=Path(sys.argv[1]))
    await tool.execute(pattern="absent")
    tool._MAX_SCAN_SECONDS = 0.2
    task = asyncio.create_task(tool.execute(pattern="(a|aa)+$", output_mode=sys.argv[2]))
    ticks = 0
    while not task.done():
        await asyncio.sleep(0.01)
        ticks += 1
    result = await task
    assert is_tool_error_result(result), result
    assert result.startswith("Error: grep scan exceeded 0.2 seconds"), result
    assert ticks >= 3, f"Event loop was blocked during regex evaluation: {ticks} ticks"
    print("PASS: pathological match stopped at the scan budget; other tasks remained responsive")

asyncio.run(main())
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), mode],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS:" in result.stdout
