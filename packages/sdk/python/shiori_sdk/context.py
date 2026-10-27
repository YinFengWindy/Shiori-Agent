"""Payload-free context budget observations, including manual and failed work."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContextBudgetObserved:
    """A request/window owner's staged budget facts; never contains prompt payloads.

    ``status`` is a mapping so a publisher can hand watchers a read-only view.
    The kernel rejects a dict field. Bus listeners still receive the original
    dict from the publisher.
    """

    session_key: str
    context_key: str
    status: Mapping[str, Any]
