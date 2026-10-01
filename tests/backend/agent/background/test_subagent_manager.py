import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest

from agent.background.subagent_manager import SubagentManager
from agent.policies.delegation import SpawnDecision, SpawnDecisionMeta
from agent.provider import LLMResponse
from bus.events import SpawnCompletionItem
from bus.queue import MessageBus
from bootstrap.runtime.generations import RuntimeCandidate
from core.common.runtime_scope import bind_runtime


@pytest.mark.asyncio
async def test_detached_job_and_queued_completion_retain_original_generation(tmp_path):
    core = SimpleNamespace(
        assert_hot_unloadable=Mock(),
        stop=AsyncMock(),
        memory_runtime=SimpleNamespace(aclose=AsyncMock()),
    )
    generation = RuntimeCandidate(1, core, SimpleNamespace(), published=True)
    parent = generation.acquire()
    bus = MessageBus()
    manager = SubagentManager(
        provider=cast(Any, _Provider()),
        workspace=tmp_path,
        bus=bus,
        model="old",
        max_tokens=256,
        fetch_requester=object(),
    )
    started = asyncio.Event()
    finish = asyncio.Event()

    async def run(**kwargs):
        started.set()
        await finish.wait()
        await manager._announce_result(
            job_id=kwargs["job_id"],
            label="job",
            task="task",
            origin_channel="desktop",
            origin_chat_id="role:test",
            status="completed",
            exit_reason="completed",
            result="result",
            decision=None,
        )

    manager._run_subagent = run
    with bind_runtime(parent):
        await manager.spawn(
            task="task",
            label="job",
            origin_channel="desktop",
            origin_chat_id="role:test",
        )
    await started.wait()
    await generation.retire()
    await parent.release()
    assert not generation.closed
    finish.set()
    await manager.drain()
    item = await bus.consume_inbound()
    assert item.runtime_lease.generation == 1
    assert not generation.closed
    await item.runtime_lease.release()
    for _ in range(5):
        await asyncio.sleep(0)
    assert generation.closed
    core.stop.assert_awaited_once()


class _Provider:
    async def chat(self, **kwargs: Any) -> LLMResponse:
        raise AssertionError("provider.chat should not be called in this test")


@pytest.mark.asyncio
async def test_subagent_manager_spawn_is_non_blocking(tmp_path):
    bus = MessageBus()
    manager = SubagentManager(
        provider=cast(Any, _Provider()),
        workspace=tmp_path,
        bus=bus,
        model="m",
        max_tokens=256,
        fetch_requester=object(),  # type: ignore[arg-type]
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def _fake_run_subagent(**kwargs):
        started.set()
        await release.wait()

    manager._run_subagent = _fake_run_subagent  # type: ignore[assignment]

    text = await manager.spawn(
        task="do work",
        label="job",
        origin_channel="telegram",
        origin_chat_id="123",
        decision=SpawnDecision(
            should_spawn=True,
            label="job",
            meta=SpawnDecisionMeta(
                source="heuristic",
                confidence="high",
                reason_code="long_running",
            ),
        ),
    )

    assert "已创建后台任务" in text
    await asyncio.wait_for(started.wait(), timeout=0.2)
    assert manager.get_running_count() == 1

    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert manager.get_running_count() == 0


@pytest.mark.asyncio
async def test_subagent_manager_announces_completion_to_origin_session(tmp_path):
    bus = MessageBus()
    manager = SubagentManager(
        provider=cast(Any, _Provider()),
        workspace=tmp_path,
        bus=bus,
        model="m",
        max_tokens=256,
        fetch_requester=object(),  # type: ignore[arg-type]
    )

    class _FakeSubAgent:
        last_exit_reason = "forced_summary"
        last_usage = {"cumulative": {"prompt_tokens": 7}}

        async def run(self, task: str) -> str:
            assert task == "research this"
            return "已完成检索，剩余整理，下一步继续"

    manager._build_subagent = (
        lambda *, task_dir, profile="research": _FakeSubAgent()
    )  # type: ignore[assignment]

    await manager.spawn(
        task="research this",
        label="research",
        origin_channel="telegram",
        origin_chat_id="42",
        decision=SpawnDecision(
            should_spawn=True,
            label="research",
            meta=SpawnDecisionMeta(
                source="heuristic",
                confidence="medium",
                reason_code="context_isolation_needed",
            ),
        ),
    )

    item = await asyncio.wait_for(bus.consume_inbound(), timeout=0.2)

    assert isinstance(item, SpawnCompletionItem)
    assert item.channel == "telegram"
    assert item.chat_id == "42"
    assert item.event.status == "incomplete"
    assert item.event.exit_reason == "forced_summary"
    assert item.decision is not None
    assert item.decision.meta.reason_code == "context_isolation_needed"

    trace_path = tmp_path / "memory" / "spawn_trace.jsonl"
    lines = [
        line for line in trace_path.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(lines) == 2
    started = __import__("json").loads(lines[0])
    completed = __import__("json").loads(lines[1])
    assert started["trace_type"] == "spawn"
    assert started["subject"]["kind"] == "job"
    assert completed["payload"]["status"] == "incomplete"
    assert completed["payload"]["request_usage"]["cumulative"]["prompt_tokens"] == 7


@pytest.mark.asyncio
async def test_subagent_manager_lists_and_cancels_running_job(tmp_path):
    bus = MessageBus()
    manager = SubagentManager(
        provider=cast(Any, _Provider()),
        workspace=tmp_path,
        bus=bus,
        model="m",
        max_tokens=256,
        fetch_requester=object(),  # type: ignore[arg-type]
    )

    class _WaitingSubAgent:
        last_exit_reason = "running"

        async def run(self, task: str) -> str:
            await asyncio.Future()
            return "never"

    manager._build_subagent = (
        lambda *, task_dir, profile="research": _WaitingSubAgent()
    )  # type: ignore[assignment]

    await manager.spawn(
        task="long task",
        label="long",
        origin_channel="telegram",
        origin_chat_id="42",
    )

    jobs = manager.list_running_jobs()
    assert len(jobs) == 1
    job_id = str(jobs[0]["job_id"])
    assert jobs[0]["label"] == "long"
    assert await manager.cancel(job_id) is True

    item = await asyncio.wait_for(bus.consume_inbound(), timeout=0.2)
    assert isinstance(item, SpawnCompletionItem)
    assert item.event.status == "cancelled"
    assert item.event.exit_reason == "cancelled"
    await asyncio.sleep(0)
    assert manager.get_running_count() == 0


@pytest.mark.asyncio
async def test_spawn_sync_uses_shorter_iteration_budget(tmp_path):
    bus = MessageBus()
    manager = SubagentManager(
        provider=cast(Any, _Provider()),
        workspace=tmp_path,
        bus=bus,
        model="m",
        max_tokens=256,
        fetch_requester=object(),  # type: ignore[arg-type]
    )
    observed: dict[str, object] = {}

    class _FakeSubAgent:
        last_exit_reason = "completed"
        last_usage = {"cumulative": {"prompt_tokens": 9}}

        async def run(self, task: str) -> str:
            return "ok"

    def _fake_build_subagent(*, task_dir, profile="research", max_iterations=50):
        observed["task_dir"] = task_dir
        observed["profile"] = profile
        observed["max_iterations"] = max_iterations
        return _FakeSubAgent()

    manager._build_subagent = _fake_build_subagent  # type: ignore[assignment]

    result = await manager.spawn_sync(task="research this", label="job")

    assert "退出原因: completed" in result
    assert observed["profile"] == "research"
    assert observed["max_iterations"] == 10
    trace = __import__("json").loads(
        (tmp_path / "memory" / "spawn_trace.jsonl").read_text(encoding="utf-8")
    )
    assert trace["payload"]["request_usage"]["cumulative"]["prompt_tokens"] == 9


@pytest.mark.asyncio
async def test_spawn_sync_uses_the_origin_role_model_snapshot(tmp_path):
    activations: list[tuple[str, str]] = []

    class _RoleRuntimeRegistry:
        async def get(self, role_id: str):
            self.role_id = role_id
            return self

        @contextmanager
        def activate_model(self, purpose: str):
            activations.append((self.role_id, purpose))
            yield SimpleNamespace(provider=cast(Any, _Provider()), model="role-model")

    manager = SubagentManager(
        provider=cast(Any, _Provider()),
        workspace=tmp_path,
        bus=MessageBus(),
        model="base-model",
        max_tokens=256,
        fetch_requester=object(),  # type: ignore[arg-type]
        role_runtime_registry=_RoleRuntimeRegistry(),
    )
    observed: dict[str, object] = {}

    class _FakeSubAgent:
        last_exit_reason = "completed"

        async def run(self, _task: str) -> str:
            return "ok"

    def _fake_build_subagent(**kwargs):
        observed["runtime"] = kwargs["runtime"]
        return _FakeSubAgent()

    manager._build_subagent = _fake_build_subagent  # type: ignore[assignment]

    await manager.spawn_sync(task="research this", label="job", role_id="mira")

    runtime = observed["runtime"]
    assert activations == [("mira", "chat")]
    assert getattr(runtime, "model") == "role-model"
