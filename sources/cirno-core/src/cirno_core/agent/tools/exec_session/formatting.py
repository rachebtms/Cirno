"""Human/model-readable execution session results."""

from cirno_core.processes.sessions.contracts import SessionPoll


def format_session_poll(session_id: str, poll: SessionPoll) -> str:
    parts = [poll.output] if poll.output else []
    if poll.truncated_chars:
        parts.append(f"({poll.truncated_chars:,} chars truncated from output)")
    if poll.finish_reason == "max_runtime":
        parts.append("Error: Command timed out; session was terminated. Reason: max_runtime.")
    elif poll.finish_reason == "idle_timeout":
        parts.append(
            "Error: Output silence limit reached; session was terminated. Reason: idle_timeout."
        )
    elif poll.terminated:
        parts.append(f"Session terminated. Reason: {poll.finish_reason}.")
    elif poll.finish_reason == "execution_error":
        parts.append(
            f"Error: Command output failed: {poll.execution_error}. Reason: execution_error."
        )
    if poll.output_incomplete:
        parts.append("Output collection ended before EOF; output may be incomplete.")
    if poll.stdin_closed:
        parts.append("Stdin closed.")
    if poll.done:
        parts.append(f"Exit code: {poll.exit_code}")
    else:
        state = "stopping" if poll.stopping else "running"
        parts.append(f"Process {state}. session_id: {session_id}")
        if poll.idle_timeout and poll.output_idle_s >= poll.idle_timeout:
            parts.append(
                f"Output silent for {poll.output_idle_s:.1f}s; "
                "no stdout/stderr bytes observed. This does not establish a stall."
            )
        remaining = "unlimited" if poll.remaining_s is None else f"{poll.remaining_s:.1f}s"
        parts.append(f"Runtime remaining: {remaining}")
    parts.append(f"Elapsed: {poll.elapsed_s:.1f}s")
    return "\n".join(parts) if parts else "(no output yet)"
