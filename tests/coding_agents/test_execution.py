from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from coding_agents.adapters import (
    AdapterError,
    AdapterEvent,
    AdapterResult,
    PreparedRun,
    ProbeResult,
    ResumeSpec,
    RunHandle,
    TaskRunSpec,
)
from coding_agents.execution import AdapterExecutor, AdapterRegistry
from coding_agents.models import Provider


class _Process:
    async def stdout_lines(self) -> AsyncIterator[bytes]:
        if False:
            yield b""

    async def stderr_lines(self) -> AsyncIterator[bytes]:
        if False:
            yield b""

    async def wait(self) -> int:
        return 0

    async def stop(self, grace_seconds: float = 3.0) -> None:
        return None


class _FakeAdapter:
    def __init__(
        self,
        *,
        block_stream: bool = False,
        block_start: bool = False,
        stream_error: Exception | None = None,
    ) -> None:
        self.block_stream = block_stream
        self.block_start = block_start
        self.stream_error = stream_error
        self.start_gate = asyncio.Event()
        self.stream_gate = asyncio.Event()
        self.started = asyncio.Event()
        self.calls: list[str] = []

    async def probe(self) -> ProbeResult:
        self.calls.append("probe")
        return ProbeResult(True, version="fake 1.0")

    def prepare(self, spec: TaskRunSpec) -> PreparedRun:
        self.calls.append("prepare")
        return self._prepared(spec)

    def _prepared(self, spec: TaskRunSpec) -> PreparedRun:
        return PreparedRun(
            spec=spec,
            command=("fake",),
            cwd=spec.worktree,
            stdin=spec.task.encode(),
            environment={},
        )

    async def start(self, prepared: PreparedRun) -> RunHandle:
        self.calls.append("start")
        self.started.set()
        if self.block_start:
            await self.start_gate.wait()
        return RunHandle(prepared, _Process())

    async def _stream(self, handle: RunHandle) -> AsyncIterator[AdapterEvent]:
        self.calls.append("stream")
        event = AdapterEvent("process_started", {"run_id": handle.prepared.spec.run_id})
        handle.events.append(event)
        yield event
        if self.stream_error is not None:
            raise self.stream_error
        if self.block_stream:
            await self.stream_gate.wait()
        handle.exit_code = -9 if handle.cancelled else 0
        exited = AdapterEvent("process_exited", {"exit_code": handle.exit_code})
        handle.events.append(exited)
        yield exited

    def stream(self, handle: RunHandle) -> AsyncIterator[AdapterEvent]:
        return self._stream(handle)

    async def cancel(self, handle: RunHandle) -> None:
        self.calls.append("cancel")
        handle.cancelled = True
        handle.exit_code = -9
        self.stream_gate.set()

    async def collect_result(self, handle: RunHandle) -> AdapterResult:
        self.calls.append("collect_result")
        event = AdapterEvent("result_collected", {"success": not handle.cancelled})
        handle.events.append(event)
        return AdapterResult(
            success=not handle.cancelled and not handle.timed_out,
            exit_code=handle.exit_code or 0,
            summary="done",
            session_id=None,
            error_code=handle.error_code,
            error_message=handle.error_message,
        )

    def resume(self, spec: ResumeSpec) -> PreparedRun:
        self.calls.append("resume")
        return self._prepared(spec.run)

    async def cleanup(self, handle: RunHandle) -> None:
        self.calls.append("cleanup")
        if handle.exit_code is None:
            await self.cancel(handle)


def _spec(tmp_path: Path, *, run_id: str = "run-1", timeout: float = 1) -> TaskRunSpec:
    return TaskRunSpec(
        run_id=run_id,
        task="do work",
        worktree=tmp_path,
        model="fake",
        effort="medium",
        permission_level="workspace-write",
        timeout_seconds=timeout,
    )


def test_registry_routes_provider_and_rejects_duplicates() -> None:
    codex = _FakeAdapter()
    registry = AdapterRegistry({Provider.CODEX: codex})

    assert registry.get("codex") is codex
    assert registry.providers == (Provider.CODEX,)
    with pytest.raises(ValueError, match="已注册"):
        registry.register(Provider.CODEX, _FakeAdapter())
    with pytest.raises(AdapterError) as raised:
        registry.get(Provider.CLAUDE)
    assert raised.value.code == "provider_unavailable"


@pytest.mark.asyncio
async def test_registry_probes_all_adapters() -> None:
    codex = _FakeAdapter()
    claude = _FakeAdapter()
    registry = AdapterRegistry(
        {Provider.CODEX: codex, Provider.CLAUDE: claude}
    )

    results = await registry.probe_all()

    assert set(results) == {Provider.CODEX, Provider.CLAUDE}
    assert all(result.available for result in results.values())
    assert codex.calls == ["probe"]
    assert claude.calls == ["probe"]


@pytest.mark.asyncio
async def test_execute_runs_full_lifecycle_and_emits_result_event(
    tmp_path: Path,
) -> None:
    adapter = _FakeAdapter()
    executor = AdapterExecutor(AdapterRegistry({Provider.CODEX: adapter}))
    events: list[str] = []

    async def on_event(event: AdapterEvent) -> None:
        events.append(event.event_type)

    result = await executor.execute(
        Provider.CODEX,
        _spec(tmp_path),
        on_event=on_event,
    )

    assert result.success is True
    assert adapter.calls == [
        "prepare",
        "start",
        "stream",
        "collect_result",
        "cleanup",
    ]
    assert events == ["process_started", "process_exited", "result_collected"]
    assert await executor.cancel("run-1") is False


@pytest.mark.asyncio
async def test_execute_timeout_cancels_and_returns_timeout_result(
    tmp_path: Path,
) -> None:
    adapter = _FakeAdapter(block_stream=True)
    executor = AdapterExecutor(AdapterRegistry({Provider.CODEX: adapter}))
    events: list[str] = []

    result = await executor.execute(
        Provider.CODEX,
        _spec(tmp_path, timeout=0.001),
        on_event=lambda event: events.append(event.event_type),
    )

    assert result.success is False
    assert result.error_code == "process_timeout"
    assert "cancel" in adapter.calls
    assert events[-3:] == [
        "adapter_error",
        "process_exited",
        "result_collected",
    ]


@pytest.mark.asyncio
async def test_start_timeout_returns_stable_error(tmp_path: Path) -> None:
    adapter = _FakeAdapter(block_start=True)
    executor = AdapterExecutor(AdapterRegistry({Provider.CODEX: adapter}))
    events: list[str] = []

    result = await executor.execute(
        Provider.CODEX,
        _spec(tmp_path, timeout=0.001),
        on_event=lambda event: events.append(event.event_type),
    )

    assert result.error_code == "process_timeout"
    assert result.exit_code == -1
    assert events == ["adapter_error"]
    assert await executor.cancel("run-1") is False


@pytest.mark.asyncio
async def test_cancel_requested_while_starting_is_applied(tmp_path: Path) -> None:
    adapter = _FakeAdapter(block_start=True)
    executor = AdapterExecutor(AdapterRegistry({Provider.CLAUDE: adapter}))
    events: list[str] = []
    execution = asyncio.create_task(
        executor.execute(
            Provider.CLAUDE,
            _spec(tmp_path),
            on_event=lambda event: events.append(event.event_type),
        )
    )
    await adapter.started.wait()

    assert await executor.cancel("run-1") is True
    adapter.start_gate.set()
    result = await execution

    assert result.success is False
    assert adapter.calls == [
        "prepare",
        "start",
        "cancel",
        "collect_result",
        "cleanup",
    ]
    assert events == ["process_exited", "result_collected"]


@pytest.mark.asyncio
async def test_duplicate_active_run_is_rejected(tmp_path: Path) -> None:
    adapter = _FakeAdapter(block_start=True)
    executor = AdapterExecutor(AdapterRegistry({Provider.CODEX: adapter}))
    first = asyncio.create_task(executor.execute(Provider.CODEX, _spec(tmp_path)))
    await adapter.started.wait()

    with pytest.raises(AdapterError) as raised:
        await executor.execute(Provider.CODEX, _spec(tmp_path))
    assert raised.value.code == "process_start_failed"

    await executor.cancel("run-1")
    adapter.start_gate.set()
    await first


@pytest.mark.asyncio
async def test_running_cancel_finishes_and_releases_active_run(
    tmp_path: Path,
) -> None:
    adapter = _FakeAdapter(block_stream=True)
    executor = AdapterExecutor(AdapterRegistry({Provider.CODEX: adapter}))
    process_started = asyncio.Event()

    def on_event(event: AdapterEvent) -> None:
        if event.event_type == "process_started":
            process_started.set()

    execution = asyncio.create_task(
        executor.execute(Provider.CODEX, _spec(tmp_path), on_event=on_event)
    )
    await process_started.wait()

    assert await executor.cancel("run-1") is True
    result = await execution

    assert result.success is False
    assert adapter.calls[-3:] == ["cancel", "collect_result", "cleanup"]
    assert await executor.cancel("run-1") is False


@pytest.mark.asyncio
async def test_stream_error_cleans_up_and_releases_run(tmp_path: Path) -> None:
    adapter = _FakeAdapter(stream_error=RuntimeError("stream failed"))
    executor = AdapterExecutor(AdapterRegistry({Provider.CODEX: adapter}))

    with pytest.raises(RuntimeError, match="stream failed"):
        await executor.execute(Provider.CODEX, _spec(tmp_path))

    assert adapter.calls[-2:] == ["cleanup", "cancel"]
    assert await executor.cancel("run-1") is False


@pytest.mark.asyncio
async def test_resume_uses_explicit_adapter_path_and_emits_events(
    tmp_path: Path,
) -> None:
    adapter = _FakeAdapter()
    executor = AdapterExecutor(AdapterRegistry({Provider.CODEX: adapter}))
    events: list[str] = []

    result = await executor.resume(
        Provider.CODEX,
        ResumeSpec(_spec(tmp_path), "session-1"),
        on_event=lambda event: events.append(event.event_type),
    )

    assert result.success is True
    assert adapter.calls == [
        "resume",
        "start",
        "stream",
        "collect_result",
        "cleanup",
    ]
    assert events == ["process_started", "process_exited", "result_collected"]


@pytest.mark.asyncio
async def test_resume_preserves_duplicate_guard_and_starting_cancel(
    tmp_path: Path,
) -> None:
    adapter = _FakeAdapter(block_start=True)
    executor = AdapterExecutor(AdapterRegistry({Provider.CLAUDE: adapter}))
    resume_spec = ResumeSpec(_spec(tmp_path), "session-1")
    first = asyncio.create_task(executor.resume(Provider.CLAUDE, resume_spec))
    await adapter.started.wait()

    with pytest.raises(AdapterError) as raised:
        await executor.resume(Provider.CLAUDE, resume_spec)
    assert raised.value.code == "process_start_failed"
    assert await executor.cancel("run-1") is True

    adapter.start_gate.set()
    result = await first
    assert result.success is False


@pytest.mark.asyncio
async def test_resume_preserves_lifecycle_timeout(tmp_path: Path) -> None:
    adapter = _FakeAdapter(block_stream=True)
    executor = AdapterExecutor(AdapterRegistry({Provider.CODEX: adapter}))

    result = await executor.resume(
        Provider.CODEX,
        ResumeSpec(_spec(tmp_path, timeout=0.001), "session-1"),
    )

    assert result.error_code == "process_timeout"
    assert "cancel" in adapter.calls
