from __future__ import annotations

import asyncio
from types import SimpleNamespace

from core.memory.runtime import MemoryRuntime


class _MarkdownStub:
    def read_long_term(self, *, session_metadata=None) -> str:
        role_id = str((session_metadata or {}).get("role_id") or "")
        return f"long:{role_id}"

    def read_self(self, *, session_metadata=None) -> str:
        role_id = str((session_metadata or {}).get("role_id") or "")
        return f"self:{role_id}"

    def read_recent_context(self, *, session_metadata=None) -> str:
        role_id = str((session_metadata or {}).get("role_id") or "")
        return f"recent:{role_id}"

    def read_recent_history(self, *, max_chars=0, session_metadata=None) -> str:
        role_id = str((session_metadata or {}).get("role_id") or "")
        return f"history:{role_id}:{max_chars}"

    def get_memory_context(self, *, session_metadata=None) -> str:
        role_id = str((session_metadata or {}).get("role_id") or "")
        return f"context:{role_id}"


def test_memory_runtime_bind_session_metadata_is_task_local() -> None:
    runtime = MemoryRuntime(
        markdown=_MarkdownStub(),  # type: ignore[arg-type]
        engine=SimpleNamespace(),
    )
    first_ready = asyncio.Event()
    second_ready = asyncio.Event()
    release = asyncio.Event()

    async def _read(role_id: str, ready: asyncio.Event, wait_for: asyncio.Event) -> str:
        runtime.bind_session_metadata({"role_id": role_id})
        ready.set()
        await wait_for.wait()
        return runtime.read_self()

    async def _run() -> tuple[str, str]:
        first_task = asyncio.create_task(_read("mira", first_ready, release))
        second_task = asyncio.create_task(_read("atlas", second_ready, first_ready))
        await second_ready.wait()
        release.set()
        return await asyncio.gather(first_task, second_task)

    first, second = asyncio.run(_run())

    assert first == "self:mira"
    assert second == "self:atlas"


def test_memory_runtime_bind_session_metadata_none_clears_current_task_state() -> None:
    runtime = MemoryRuntime(
        markdown=_MarkdownStub(),  # type: ignore[arg-type]
        engine=SimpleNamespace(),
    )

    runtime.bind_session_metadata({"role_id": "mira"})
    assert runtime.read_long_term() == "long:mira"

    runtime.bind_session_metadata(None)
    assert runtime.read_long_term() == "long:"
