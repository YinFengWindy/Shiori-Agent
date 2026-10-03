"""Best-effort resource release with explicit error propagation at lifecycle boundaries."""

import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


async def run_cleanup_steps(
    *steps: tuple[str, Callable[[], Awaitable[None]]],
    aggregate_errors: bool = False,
) -> None:
    """Attempts all cleanup, reporting the first failure or an explicit error group."""
    errors: list[Exception] = []
    for name, step in steps:
        try:
            await step()
        except Exception as exc:
            errors.append(exc)
            logger.warning("shutdown step failed: %s: %s", name, exc)
    if errors:
        if aggregate_errors:
            raise ExceptionGroup("Cleanup steps failed", errors)
        raise errors[0]
