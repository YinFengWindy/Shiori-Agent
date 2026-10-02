"""Minimal model operations required by auxiliary plugin tasks."""

from typing import Literal, Protocol
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager


class ModelResponse(Protocol):
    """Model text, without requiring a host provider implementation."""

    @property
    def content(self) -> str | None: ...


class ModelToolCall(Protocol):
    """One model-proposed tool invocation with detached arguments."""

    @property
    def name(self) -> str: ...
    @property
    def arguments(self) -> dict[str, object]: ...


class ChatResponse(ModelResponse, Protocol):
    """Text and tool proposals consumed by screen and scene observers."""

    @property
    def tool_calls(self) -> Sequence[ModelToolCall]: ...


class ModelProvider(Protocol):
    """Runs a bounded chat request using the injected provider's routing."""

    async def chat(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
        model: str,
        max_tokens: int | None,
        *,
        call_purpose: Literal["default", "auxiliary"] = "default",
    ) -> ModelResponse: ...


class ChatProvider(Protocol):
    """Chat options used by vision observation with payload retention disabled."""

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
    ) -> ChatResponse: ...


class ModelSnapshot(Protocol):
    """An activated provider/model pair retained across awaited plugin work."""

    @property
    def provider(self) -> ChatProvider: ...
    @property
    def model(self) -> str: ...


class RoleModels(Protocol):
    """Resolve one role purpose without exposing the runtime registry."""

    def activate(
        self, role_id: str, purpose: Literal["chat", "vision"]
    ) -> AbstractAsyncContextManager[ModelSnapshot]: ...
