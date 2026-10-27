"""Undo command business outcomes through the sessions and memory sockets."""

from typing import Any, cast

import pytest
from plugins.plugin_undo.backend.plugin import PluginUndo, setup
from shiori_sdk.commands import CommandInput, CommandRegistry
from shiori_sdk.core.conversation import COMMANDS
from shiori_sdk.core.memory import MEMORY_ENGINE
from shiori_sdk.core.sessions import SESSIONS, RollbackResult
from shiori_sdk.kernel import Kernel, PluginSpec
from shiori_sdk.memory.engine import TurnRollback
from shiori_sdk.testing.commands import FakeSessionUndo
from shiori_sdk.testing.extensions import FakeExtensionContext


def _rolled_back() -> RollbackResult:
    return RollbackResult(
        "cli:1:0",
        ("cli:1:0", "cli:1:1"),
        "cli:1:0",
        "cli:1:1",
        0,
        2,
        0,
    )


def _context(manager, memory=None) -> tuple[FakeExtensionContext, CommandRegistry]:
    kernel, commands = Kernel(), CommandRegistry()
    kernel.provide(COMMANDS, commands)
    kernel.provide(SESSIONS, manager)
    if memory is not None:
        kernel.provide(MEMORY_ENGINE, cast(Any, memory))
    ctx = FakeExtensionContext(
        "plugin_undo",
        kernel=kernel,
        inject=("sessions", "commands"),
        optional_inject=("memory_engine",),
    )
    return ctx, commands


class _MemoryEngine:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.fail = fail
        self.superseded = False

    def rollback_turn(self, turn_id: str) -> TurnRollback:
        self.calls.append(turn_id)
        if self.fail:
            raise RuntimeError("memory rollback failed")
        self.superseded = True
        return TurnRollback(
            affected_ids=("mem1",),
            restored_ids=("old1",),
            rollback_source_ids=("cli:1:0", "cli:1:1", "cli:1:2"),
        )


@pytest.mark.asyncio
async def test_undo_rolls_memory_back_before_the_session():
    order: list[str] = []
    manager = FakeSessionUndo(_rolled_back())
    memory = _MemoryEngine()

    real_rollback = memory.rollback_turn
    real_session = manager.rollback_last_turn

    def rollback_turn(turn_id: str) -> TurnRollback:
        order.append("memory")
        return real_rollback(turn_id)

    async def rollback_last_turn(session_key, *, rollback_source_ids=None):
        order.append("session")
        return await real_session(session_key, rollback_source_ids=rollback_source_ids)

    memory.rollback_turn = rollback_turn
    manager.rollback_last_turn = rollback_last_turn

    reply = await PluginUndo(manager, lambda: cast(Any, memory)).undo("cli:1")

    assert order == ["memory", "session"]
    assert memory.calls == ["cli:1:0"]
    assert manager.deleted
    assert manager.source_ids == ["cli:1:0", "cli:1:1", "cli:1:2"]
    assert reply == (
        "已撤销上一轮对话。\n删除消息：2 条\n失效记忆：1 条\n恢复旧记忆：1 条"
    )


@pytest.mark.asyncio
async def test_session_failure_after_memory_rollback_keeps_the_memory_change(caplog):
    manager = FakeSessionUndo(_rolled_back())
    memory = _MemoryEngine()

    async def rollback_last_turn(session_key, *, rollback_source_ids=None):
        manager.calls.append(session_key)
        manager.source_ids = list(rollback_source_ids or [])
        raise RuntimeError("session rollback failed")

    manager.rollback_last_turn = rollback_last_turn
    reply = await PluginUndo(manager, lambda: cast(Any, memory)).undo("cli:1")

    assert memory.superseded
    assert not manager.deleted
    assert "已撤销上一轮对话" not in reply
    assert "会话撤销失败" in reply
    assert "失效记忆：1 条" in reply
    assert "恢复旧记忆：1 条" in reply
    assert "session=cli:1" in caplog.text
    assert "mem1" in caplog.text


@pytest.mark.asyncio
async def test_memory_failure_leaves_the_session(caplog):
    manager = FakeSessionUndo(_rolled_back())
    memory = _MemoryEngine(fail=True)
    reply = await PluginUndo(manager, lambda: cast(Any, memory)).undo("cli:1")
    assert reply == "记忆回滚失败，上一轮对话还在。可以重试。"
    assert memory.calls == ["cli:1:0"]
    assert manager.calls == []
    assert not manager.deleted
    assert not memory.superseded
    assert "turn_id=cli:1:0" in caplog.text


@pytest.mark.asyncio
async def test_no_passive_turn_does_not_roll_memory_back():
    class _DeletesOnCall(FakeSessionUndo):
        async def rollback_last_turn(self, session_key, *, rollback_source_ids=None):
            self.deleted = True
            return None

    memory = _MemoryEngine()
    manager = _DeletesOnCall()
    assert (
        await PluginUndo(manager, lambda: cast(Any, memory)).undo("cli:1")
        == "没有可撤销的上一轮对话。"
    )
    assert not memory.superseded
    assert not manager.deleted


@pytest.mark.asyncio
async def test_missing_memory_still_undoes_session():
    """An empty memory socket rolls the session back even if no turn id is readable."""

    class _NoTurnId(FakeSessionUndo):
        def last_passive_turn_id(self, session_key: str) -> str | None:
            self.turn_lookups.append(session_key)
            return None

    manager = _NoTurnId(_rolled_back())
    reply = await PluginUndo(manager, lambda: None).undo("cli:1")
    assert manager.deleted
    assert manager.source_ids is None
    assert reply == (
        "已撤销上一轮对话。\n删除消息：2 条\n失效记忆：0 条\n恢复旧记忆：0 条"
    )


@pytest.mark.asyncio
async def test_session_error_without_memory_propagates():
    manager = FakeSessionUndo(_rolled_back())

    async def rollback_last_turn(session_key, *, rollback_source_ids=None):
        raise RuntimeError("session down")

    manager.rollback_last_turn = rollback_last_turn
    with pytest.raises(RuntimeError, match="session down"):
        await PluginUndo(manager, lambda: None).undo("cli:1")


@pytest.mark.asyncio
async def test_session_without_a_turn_after_memory_rollback_does_not_claim_undo():
    manager = FakeSessionUndo(_rolled_back())
    memory = _MemoryEngine()

    async def rollback_last_turn(session_key, *, rollback_source_ids=None):
        manager.calls.append(session_key)
        return None

    manager.rollback_last_turn = rollback_last_turn
    reply = await PluginUndo(manager, lambda: cast(Any, memory)).undo("cli:1")
    assert memory.superseded
    assert "已撤销上一轮对话" not in reply
    assert reply == (
        "会话里已经没有可撤销的上一轮，但记忆已回滚。\n失效记忆：1 条\n恢复旧记忆：1 条"
    )


@pytest.mark.asyncio
async def test_setup_and_unload_register_one_command():
    ctx, commands = _context(FakeSessionUndo())
    await setup(ctx)
    assert commands.menu() == [("undo", "撤销上一轮对话")]
    await ctx.aclose()
    assert commands.menu() == [] and commands.handler("/undo") is None


@pytest.mark.asyncio
async def test_undo_reads_the_engine_again_after_reload():
    """The next undo rolls back whichever engine is provided after a reload."""
    kernel = Kernel()
    commands = CommandRegistry()
    kernel.provide(COMMANDS, commands)
    generation = {"n": 1}

    class _GenerationEngine:
        def __init__(self, generation_id: int) -> None:
            self.generation_id = generation_id
            self.calls: list[str] = []

        def rollback_turn(self, turn_id: str) -> TurnRollback:
            self.calls.append(turn_id)
            return TurnRollback(
                affected_ids=tuple(
                    f"mem-{self.generation_id}-{index}"
                    for index in range(self.generation_id)
                )
            )

    engines: list[_GenerationEngine] = []

    async def provide_engine(ctx) -> None:
        engine = _GenerationEngine(generation["n"])
        engines.append(engine)
        ctx.provide(MEMORY_ENGINE, cast(Any, engine))

    await kernel.start(
        [PluginSpec("memory", provide_engine, provides=("memory_engine",))]
    )
    manager = FakeSessionUndo(_rolled_back())
    kernel.provide(SESSIONS, manager)
    ctx = FakeExtensionContext(
        "plugin_undo",
        kernel=kernel,
        inject=("sessions", "commands"),
        optional_inject=("memory_engine",),
    )
    await setup(ctx)
    handler = commands.handler("/undo")
    assert handler is not None
    first = await handler(CommandInput("/undo", "cli:1"))
    generation["n"] = 2
    await kernel.reload("memory")
    second = await handler(CommandInput("/undo", "cli:1"))
    assert "失效记忆：1 条" in first
    assert "失效记忆：2 条" in second
    assert [engine.generation_id for engine in engines for _call in engine.calls] == [
        1,
        2,
    ]
    assert engines[0].calls == ["cli:1:0"]
    assert engines[1].calls == ["cli:1:0"]
    await ctx.aclose()
