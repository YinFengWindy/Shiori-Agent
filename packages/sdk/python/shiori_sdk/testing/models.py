"""Independent model responses and role activation fixtures."""

from collections.abc import Iterable
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


class FakeChatProvider:
    """Replays queued responses in order and records each chat request.

    A request with nothing queued fails the test, so a plugin that reaches the
    model unexpectedly is visible instead of silently getting an empty answer.
    """

    def __init__(self, responses: Iterable[FakeModelResponse] = ()):
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []

    async def chat(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
        model: str,
        max_tokens: int | None,
        *,
        call_purpose: Literal["default", "auxiliary"] = "default",
        tool_choice: str | dict[str, object] = "auto",
        payload_snapshot_enabled: bool | None = None,
    ) -> FakeModelResponse:
        """Record the request and return the next queued response."""
        self.requests.append(
            {
                "messages": messages,
                "tools": tools,
                "model": model,
                "max_tokens": max_tokens,
                "call_purpose": call_purpose,
                "tool_choice": tool_choice,
            }
        )
        if not self.responses:
            raise AssertionError("FakeChatProvider received an unexpected chat request")
        return self.responses.pop(0)


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
