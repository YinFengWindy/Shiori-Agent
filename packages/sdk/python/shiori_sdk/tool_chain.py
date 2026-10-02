"""Persisted tool-call values shared by committed events."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """Persisted invocation arguments and result within a committed turn."""

    call_id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    result: str = ""


@dataclass
class ToolCallGroup:
    """Assistant text and its associated group of tool invocations."""

    text: str
    calls: list[ToolCall] = field(default_factory=list)
