"""``MEMORY_OPTIMIZER``: the background memory optimizer's progress (#907 P6b).

The ``memory_optimizer`` plugin provides this key; the host never does. The
host reads it with ``get`` to show a running optimization in the role task
panel; ``None`` means the plugin is off.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from shiori_sdk.kernel import Key


@dataclass(frozen=True, kw_only=True)
class MemoryOptimizationRun:
    """The optimization running now: one role at a time.

    ``started_at`` is timezone-aware.
    """

    role_id: str
    started_at: datetime


class MemoryOptimizer(Protocol):
    """Read-only view of the process-wide optimizer."""

    def active_run(self) -> MemoryOptimizationRun | None:
        """The running optimization, or ``None`` while none runs."""
        ...


MEMORY_OPTIMIZER: Key[MemoryOptimizer] = Key("memory_optimizer")
"""The memory optimizer's progress. The ``memory_optimizer`` plugin provides this."""
