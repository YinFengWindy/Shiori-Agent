from __future__ import annotations

from pathlib import Path

import pytest

from coding_agents.adapters.base import (
    AdapterError,
    BaseCliAdapter,
    PreparedRun,
    TaskRunSpec,
)

from .conftest import FakeProcess, FakeProcessRunner


def _prepared(tmp_path: Path, *, timeout: float = 1) -> PreparedRun:
    spec = TaskRunSpec(
        run_id="run-1",
        task="修复问题",
        worktree=tmp_path,
        model="model",
        effort="medium",
        permission_level="read-only",
        timeout_seconds=timeout,
        environment={"PATH": "bin"},
    )
    return PreparedRun(
        spec=spec,
        command=("provider", "run"),
        cwd=tmp_path,
        stdin=b"prompt",
        environment=spec.environment,
    )


class _Adapter(BaseCliAdapter):
    provider = "fake"


@pytest.mark.asyncio
async def test_start_passes_parameter_array_and_cancel_is_idempotent(
    tmp_path: Path,
) -> None:
    process = FakeProcess(block=True)
    runner = FakeProcessRunner(process)
    adapter = _Adapter(runner)

    handle = await adapter.start(_prepared(tmp_path))
    await adapter.cancel(handle)
    await adapter.cancel(handle)

    assert runner.started == [
        (("provider", "run"), tmp_path, {"PATH": "bin"}, b"prompt")
    ]
    assert process.stopped is True
    assert (await adapter.collect_result(handle)).error_code == "cancelled"


@pytest.mark.asyncio
async def test_stream_timeout_stops_process_and_returns_stable_error(
    tmp_path: Path,
) -> None:
    process = FakeProcess(block=True)
    adapter = _Adapter(FakeProcessRunner(process))
    handle = await adapter.start(_prepared(tmp_path, timeout=0.001))

    events = [
        event
        async for event in adapter._stream_json_events(handle, lambda _: [])
    ]
    result = await adapter.collect_result(handle)

    assert [event.event_type for event in events] == [
        "adapter_error",
        "process_exited",
    ]
    assert process.stopped is True
    assert result.error_code == "process_timeout"


@pytest.mark.asyncio
async def test_collect_result_preserves_exit_code_and_stderr(tmp_path: Path) -> None:
    process = FakeProcess(stderr=(b"boom\n",), exit_code=7)
    adapter = _Adapter(FakeProcessRunner(process))
    handle = await adapter.start(_prepared(tmp_path))
    _ = [event async for event in adapter._stream_json_events(handle, lambda _: [])]

    result = await adapter.collect_result(handle)

    assert result.success is False
    assert result.exit_code == 7
    assert result.stderr == "boom\n"
    assert result.error_code == "process_crashed"


@pytest.mark.asyncio
async def test_collect_result_before_stream_fails(tmp_path: Path) -> None:
    adapter = _Adapter(FakeProcessRunner())
    handle = await adapter.start(_prepared(tmp_path))

    with pytest.raises(AdapterError, match="stream") as raised:
        await adapter.collect_result(handle)

    assert raised.value.code == "process_crashed"


@pytest.mark.asyncio
async def test_start_failure_has_stable_error_code(tmp_path: Path) -> None:
    adapter = _Adapter(FakeProcessRunner(start_error=FileNotFoundError("fake")))

    with pytest.raises(AdapterError) as raised:
        await adapter.start(_prepared(tmp_path))

    assert raised.value.code == "process_start_failed"
