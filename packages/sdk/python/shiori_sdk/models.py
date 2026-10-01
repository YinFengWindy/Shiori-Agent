"""Minimal model operations required by auxiliary plugin tasks."""

from typing import Literal, Protocol


class ModelResponse(Protocol):
    """Model text, without requiring a host provider implementation."""

    @property
    def content(self) -> str | None: ...


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
