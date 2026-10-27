from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from shiori_sdk.memory.engine import MemoryEngine, MemoryQuery, MemoryQueryResult

if TYPE_CHECKING:
    from core.memory.markdown import MarkdownMemoryRuntime


class EngineGetter:
    """Callable bound to this generation's ``MEMORY_ENGINE`` after the kernel exists.

    The agent loop captures the getter before plugins start. ``bind`` replaces
    what it reads without replacing the callable, so the next use sees the
    engine this generation actually provides (D25). Unbound, it answers None.
    """

    def __init__(self) -> None:
        self._get: Callable[[], MemoryEngine | None] = lambda: None

    def __call__(self) -> MemoryEngine | None:
        return self._get()

    def bind(self, get: Callable[[], MemoryEngine | None]) -> None:
        """Read ``get`` on every later call."""
        self._get = get


@dataclass
class MemoryRuntime:
    """Markdown memory and this generation's engine getter.

    ``current_engine`` is the one source every engine consumer reads. Callers
    take the getter and call it on each use, never keeping the engine itself
    (D25). It answers ``kernel.get(MEMORY_ENGINE)`` once bound, and None when
    this generation has no provider. Engine databases and embedders close with
    the providing plugin, before this runtime is closed.
    """

    markdown: "MarkdownMemoryRuntime"
    current_engine: EngineGetter = field(default_factory=EngineGetter)
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

    async def query(self, request: MemoryQuery) -> MemoryQueryResult:
        engine = self.current_engine()
        if engine is None:
            return MemoryQueryResult(trace={"mode": "disabled"})
        return await engine.query(request)

    async def aclose(self) -> None:
        """No engine resources live here; the providing plugin already closed them."""
