"""Undo command business outcomes through the sessions and memory sockets."""

from pathlib import Path
from typing import Any, cast

import pytest
from plugins.plugin_undo.backend.plugin import PluginUndo, setup
from shiori_sdk.commands import CommandInput, CommandRegistry
from shiori_sdk.core.conversation import COMMANDS
from shiori_sdk.core.memory import MEMORY_ENGINE
from shiori_sdk.core.sessions import SESSIONS, RollbackResult
from shiori_sdk.kernel import Kernel, PluginSpec
from shiori_sdk.memory.engine import TurnRollback
from shiori_sdk.testing.commands import FakeSessions
from shiori_sdk.testing.extensions import FakeExtensionContext

PACKAGE_DIR = Path(__file__).resolve().parents[1]


def _rolled_back(turn_id: str = "cli:1:0") -> RollbackResult:
    return RollbackResult(turn_id, (turn_id, "cli:1:1"), 2, 0)


def _context(manager, memory=None) -> tuple[FakeExtensionContext, CommandRegistry]:
    kernel, commands = Kernel(), CommandRegistry()
    kernel.provide(COMMANDS, commands)
    kernel.provide(SESSIONS, manager)
    if memory is not None:
        kernel.provide(MEMORY_ENGINE, cast(Any, memory))
    ctx = FakeExtensionContext(
        "plugin_undo",
        kernel=kernel,
        package_dir=PACKAGE_DIR,
    )
    return ctx, commands


class _MemoryEngine:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self.fail = fail
        self.superseded = False

    def rollback_turn(self, turn_id: str, message_ids) -> TurnRollback:
        self.calls.append((turn_id, tuple(message_ids)))
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
    manager = FakeSessions(_rolled_back())
    memory = _MemoryEngine()

    real_rollback = memory.rollback_turn
    real_session = manager.rollback_last_turn

    def rollback_turn(turn_id: str, message_ids) -> TurnRollback:
        order.append("memory")
        return real_rollback(turn_id, message_ids)

    async def rollback_last_turn(session_key, **kwargs):
        order.append("session")
        return await real_session(session_key, **kwargs)

    memory.rollback_turn = rollback_turn
    manager.rollback_last_turn = rollback_last_turn

    reply = await PluginUndo(manager, lambda: cast(Any, memory)).undo("cli:1")

    assert order == ["memory", "session"]
    # The whole turn, so a window holding only its reply is rolled back too.
    assert memory.calls == [("cli:1:0", ("cli:1:0", "cli:1:1"))]
    assert manager.deleted
    assert manager.source_ids == ("cli:1:0", "cli:1:1", "cli:1:2")
    assert reply == (
        "已撤销上一轮对话。\n删除消息：2 条\n失效记忆：1 条\n恢复旧记忆：1 条"
    )


@pytest.mark.asyncio
async def test_session_failure_after_memory_rollback_keeps_the_memory_change(caplog):
    manager = FakeSessions(_rolled_back())
    memory = _MemoryEngine()

    async def rollback_last_turn(session_key, **_kwargs):
        manager.calls.append(session_key)
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
    manager = FakeSessions(_rolled_back())
    memory = _MemoryEngine(fail=True)
    reply = await PluginUndo(manager, lambda: cast(Any, memory)).undo("cli:1")
    assert reply == "记忆回滚失败，上一轮对话还在。可以重试。"
    assert [turn_id for turn_id, _ids in memory.calls] == ["cli:1:0"]
    assert manager.calls == []
    assert not manager.deleted
    assert not memory.superseded
    assert "turn_id=cli:1:0" in caplog.text


@pytest.mark.asyncio
async def test_no_passive_turn_does_not_roll_memory_back():
    class _DeletesOnCall(FakeSessions):
        async def rollback_last_turn(self, session_key, **_kwargs):
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
    """An empty memory socket rolls the session back even if no turn is readable."""

    class _NoTurnRead(FakeSessions):
        def last_passive_turn(self, session_key: str):
            return None

    manager = _NoTurnRead(_rolled_back())
    reply = await PluginUndo(manager, lambda: None).undo("cli:1")
    assert manager.deleted
    assert manager.source_ids == ()
    assert reply == (
        "已撤销上一轮对话。\n删除消息：2 条\n失效记忆：0 条\n恢复旧记忆：0 条"
    )


@pytest.mark.asyncio
async def test_session_error_without_memory_propagates():
    manager = FakeSessions(_rolled_back())

    async def rollback_last_turn(session_key, **_kwargs):
        raise RuntimeError("session down")

    manager.rollback_last_turn = rollback_last_turn
    with pytest.raises(RuntimeError, match="session down"):
        await PluginUndo(manager, lambda: None).undo("cli:1")


@pytest.mark.asyncio
async def test_session_without_a_turn_after_memory_rollback_does_not_claim_undo():
    manager = FakeSessions(_rolled_back())
    memory = _MemoryEngine()

    async def rollback_last_turn(session_key, **_kwargs):
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
async def test_turn_committed_after_memory_rollback_is_not_deleted(caplog):
    """Memory rolled back turn A; the session now ends in B, which stays."""
    manager = FakeSessions(_rolled_back("cli:1:0"))
    memory = _MemoryEngine()
    real_rollback = memory.rollback_turn

    def rollback_turn(turn_id: str, message_ids) -> TurnRollback:
        result = real_rollback(turn_id, message_ids)
        manager.result = _rolled_back("cli:1:2")
        return result

    memory.rollback_turn = rollback_turn
    reply = await PluginUndo(manager, lambda: cast(Any, memory)).undo("cli:1")

    assert memory.superseded
    assert manager.calls == ["cli:1"]
    assert not manager.deleted
    assert reply == "已回滚上一轮的记忆，但会话里有新消息，上一轮对话未撤销。"
    assert "latest=cli:1:2" in caplog.text


@pytest.mark.asyncio
async def test_setup_and_unload_register_one_command():
    ctx, commands = _context(FakeSessions())
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

        def rollback_turn(self, turn_id: str, message_ids) -> TurnRollback:
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
    manager = FakeSessions(_rolled_back())
    kernel.provide(SESSIONS, manager)
    ctx = FakeExtensionContext(
        "plugin_undo",
        kernel=kernel,
        package_dir=PACKAGE_DIR,
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
