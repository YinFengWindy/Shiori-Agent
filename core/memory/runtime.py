from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from core.memory.engine import (
        MemoryEngine,
        MemoryMutation,
        MemoryMutationResult,
        MemoryQuery,
        MemoryQueryResult,
    )
    from core.memory.markdown import MarkdownMemoryRuntime

logger = logging.getLogger(__name__)


class _AsyncCloseable(Protocol):
    def aclose(self) -> object: ...


class _Closeable(Protocol):
    def close(self) -> object: ...


@dataclass
class MemoryRuntime:
    markdown: "MarkdownMemoryRuntime"
    engine: "MemoryEngine"
    closeables: list[object] = field(default_factory=list[object])
    _session_metadata: dict[str, Any] | None = None

    def read_long_term(self) -> str:
        return self.markdown.read_long_term(session_metadata=self._session_metadata)

    def read_self(self) -> str:
        return self.markdown.read_self(session_metadata=self._session_metadata)

    def read_member_memory(self) -> str:
        return self.markdown.read_member_memory(
            session_metadata=self._session_metadata
        )

    def read_recent_context(self) -> str:
        return self.markdown.read_recent_context(session_metadata=self._session_metadata)

    def read_recent_history(self, *, max_chars: int = 0) -> str:
        return self.markdown.read_recent_history(
            max_chars=max_chars,
            session_metadata=self._session_metadata,
        )

    def get_memory_context(self) -> str:
        return self.markdown.get_memory_context(session_metadata=self._session_metadata)

    def has_long_term_memory(self) -> bool:
        return bool(self.read_long_term().strip())

    def bind_session_metadata(
        self,
        session_metadata: dict[str, Any] | None,
    ) -> None:
        self._session_metadata = (
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
        first_error: Exception | None = None
        for closeable in reversed(self.closeables):
            try:
                if hasattr(closeable, "aclose"):
                    result = cast(_AsyncCloseable, closeable).aclose()
                    if inspect.isawaitable(result):
                        await result
                elif hasattr(closeable, "close"):
                    _ = cast(_Closeable, closeable).close()
            except Exception as exc:
                if first_error is None:
                    first_error = exc
                logger.warning(
                    "memory runtime close failed for %s: %s",
                    type(closeable).__name__,
                    exc,
                )
        if first_error is not None:
            raise first_error
