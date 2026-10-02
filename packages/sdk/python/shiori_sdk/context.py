"""Payload-free context budget observations, including manual and failed work."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContextBudgetObserved:
    """A request/window owner's staged budget facts; never contains prompt payloads."""

    session_key: str
    context_key: str
    status: dict[str, Any]
