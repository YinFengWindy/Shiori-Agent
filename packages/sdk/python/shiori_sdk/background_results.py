"""Return plugin-owned background work through its original role conversation."""

from typing import Protocol


class BackgroundResultTarget(Protocol):
    """Host-captured destination; plugins cannot choose another role or transport."""

    @property
    def role_id(self) -> str: ...
    @property
    def thread_id(self) -> str: ...

    async def report(self, result_id: str, text: str) -> bool:
        """Ask the original role to report once; False means an already attempted ID.

        Submission waits for the role's turn gate and rechecks the original
        user's binding. IDs are reserved before execution: a failed or cancelled
        report must not be blindly resent, because delivery may already have
        happened. The caller keeps its result and surfaces any exception.
        This is an in-process contract, not a durable notification queue.
        """
        ...


class BackgroundResults(Protocol):
    """Capture the current authenticated tool turn, never model-provided IDs."""

    def capture(self) -> BackgroundResultTarget:
        """Require a live user-authored role tool turn and retain its destination."""
        ...
