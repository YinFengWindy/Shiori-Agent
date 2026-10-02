"""Independent model responses and role activation fixtures."""

from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from typing import Literal
from shiori_sdk.models import ModelToolCall, ModelSnapshot


@dataclass
class FakeModelResponse:
    """Model result used by generation/observation tests without importing a provider."""

    content: str | None
    tool_calls: list[ModelToolCall] = field(default_factory=list)


@dataclass
class FakeToolCall:
    """Explicit tool proposal fixture."""

    id: str
    name: str
    arguments: dict[str, object]


class FakeModels:
    """Select explicitly seeded snapshots and record the requested role/purpose."""

    def __init__(self):
        self.snapshots: dict[tuple[str, str], ModelSnapshot] = {}
        self.activations: list[tuple[str, str]] = []

    @asynccontextmanager
    async def activate(self, role_id: str, purpose: Literal["chat", "vision"]):
        """Hold a test-supplied snapshot over an awaited operation."""
        self.activations.append((role_id, purpose))
        yield self.snapshots[role_id, purpose]
