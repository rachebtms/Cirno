"""Recoverable memory write conflicts, captured before any mutation."""


class MemoryRevisionConflict(ValueError):
    """A rejected write with the authorized, immutable current record snapshot."""

    def __init__(self, current: dict, expected_revision: int | None):
        self.current = current
        self.expected_revision = expected_revision
        self.code = (
            "memory_revision_required" if expected_revision is None
            else "memory_revision_conflict"
        )
        message = (
            "Memory revision is required before updating; no changes were saved."
            if expected_revision is None else
            f"Memory changed since revision {expected_revision}; no changes were saved."
        )
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "error": self.code,
            "message": str(self),
            "write_applied": False,
            "expected_revision": self.expected_revision,
            "current": self.current,
        }
