from __future__ import annotations

import inspect
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from shiori_sdk.memory.build import BuildResource

if TYPE_CHECKING:
    from core.memory.engine import (
        MemoryEngine,
        MemoryMutation,
        MemoryMutationResult,
        MemoryQuery,
        MemoryQueryResult,
    )
    from core.memory.markdown import MarkdownMemoryRuntime


@dataclass
class MemoryRuntime:
    """Markdown memory, the selected engine, and the engine's transferred resources."""

    markdown: "MarkdownMemoryRuntime"
    engine: "MemoryEngine"
    resources: list[BuildResource] = field(default_factory=list)
    _session_metadata_var: ContextVar[dict[str, Any] | None] = field(
        default_factory=lambda: ContextVar(
            "memory_runtime_session_metadata",
            default=None,
        ),
        init=False,
        repr=False,
    )

    def _session_metadata(self) -> dict[str, Any] | None:
        return self._session_metadata_var.get()

    def read_long_term(self) -> str:
        return self.markdown.read_long_term(session_metadata=self._session_metadata())

    def read_self(self) -> str:
        return self.markdown.read_self(session_metadata=self._session_metadata())

    def read_recent_context(self) -> str:
        return self.markdown.read_recent_context(
            session_metadata=self._session_metadata()
        )

    def read_recent_history(self, *, max_chars: int = 0) -> str:
        return self.markdown.read_recent_history(
            max_chars=max_chars,
            session_metadata=self._session_metadata(),
        )

    def get_memory_context(self) -> str:
        return self.markdown.get_memory_context(
            session_metadata=self._session_metadata()
        )

    def has_long_term_memory(self) -> bool:
        return bool(self.read_long_term().strip())

    def bind_session_metadata(
        self,
        session_metadata: dict[str, Any] | None,
    ) -> None:
        self._session_metadata_var.set(
            dict(session_metadata) if isinstance(session_metadata, dict) else None
        )

    async def query(
        self,
        request: "MemoryQuery",
    ) -> "MemoryQueryResult":
        return await self.engine.query(request)

    async def mutate(
        self,
        request: "MemoryMutation",
    ) -> "MemoryMutationResult":
        return await self.engine.mutate(request)

    async def aclose(self) -> None:
        """Runs transferred cleanups in reverse order and re-raises the first error."""
        first_error: Exception | None = None
        resources, self.resources = self.resources, []
        for resource in reversed(resources):
            try:
                result = resource.cleanup()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error
