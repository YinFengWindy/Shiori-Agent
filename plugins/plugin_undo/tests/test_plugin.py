"""Undo command business outcomes through SDK session and memory ports."""

import pytest
from plugins.plugin_undo.backend.plugin import PluginUndo, setup
from shiori_sdk.commands import CommandInput, CommandRegistry
from shiori_sdk.core.conversation import COMMANDS
from shiori_sdk.kernel import Kernel
from shiori_sdk.sessions import UndoSessionResult
from shiori_sdk.testing.commands import FakeSessionUndo
from shiori_sdk.testing.extensions import FakeExtensionContext


def _context(manager, memory=None) -> tuple[FakeExtensionContext, CommandRegistry]:
    kernel, commands = Kernel(), CommandRegistry()
    kernel.provide(COMMANDS, commands)
    ctx = FakeExtensionContext(
        "plugin_undo",
        session_manager=manager,
        memory_engine=memory,
        kernel=kernel,
        inject=("commands",),
    )
    return ctx, commands


class _MemoryEngine:
    def __init__(self, *, fail_real_undo: bool = False) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail_real_undo = fail_real_undo

    def undo_by_message_sources(
        self,
        message_ids: list[str],
        *,
        dry_run: bool = False,
    ) -> dict[str, object]:
        self.calls.append({"message_ids": list(message_ids), "dry_run": dry_run})
        if self.fail_real_undo and not dry_run:
            raise RuntimeError("memory cleanup failed")
        return {
            "affected_ids": ["mem1"],
            "restored_ids": ["old1"],
            "rollback_source_ids": ["cli:1:0", "cli:1:1", "cli:1:2"],
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_preview_then_session_delete_then_memory_cleanup(failure, caplog):
    manager = FakeSessionUndo(
        UndoSessionResult(["cli:1:0", "cli:1:1"], "cli:1:0", "cli:1:1", 0, 2, 0)
    )
    memory = _MemoryEngine(fail_real_undo=failure)
    ctx, commands = _context(manager, memory)
    await setup(ctx)
    handler = commands.handler(" /UNDO@Bot ")
    assert handler is not None
    reply = await handler(CommandInput(" /UNDO@Bot ", "cli:1"))
    assert manager.calls == ["cli:1"]
    assert manager.deleted
    assert manager.rollback_sources == ["cli:1:0", "cli:1:1", "cli:1:2"]
    assert [c["dry_run"] for c in memory.calls] == [True, False]
    assert "已撤销上一轮对话" in reply
    assert ("记忆清理失败" in reply) == failure
    assert "删除消息：2 条" in reply
    if failure:
        assert "deleted_ids=['cli:1:0', 'cli:1:1']" in caplog.text
        assert "'affected_ids': ['mem1']" in caplog.text
    else:
        assert "失效记忆：1 条" in reply
        assert "恢复旧记忆：1 条" in reply
    await ctx.aclose()


@pytest.mark.asyncio
async def test_preview_failure_prevents_session_deletion():
    manager = FakeSessionUndo(UndoSessionResult(["u", "a"], "u", "a", 0, 0, 0))

    class BrokenMemory(_MemoryEngine):
        def undo_by_message_sources(self, message_ids, *, dry_run=False):
            raise RuntimeError("preview failed")

    memory = BrokenMemory()
    with pytest.raises(RuntimeError, match="preview failed"):
        await PluginUndo(manager, lambda: memory).undo("cli:1")
    assert not manager.deleted


@pytest.mark.asyncio
async def test_no_passive_turn_does_not_touch_memory():
    memory = _MemoryEngine()
    assert (
        await PluginUndo(FakeSessionUndo(), lambda: memory).undo("cli:1")
        == "没有可撤销的上一轮对话。"
    )
    assert memory.calls == []


@pytest.mark.asyncio
async def test_missing_memory_still_undoes_session():
    manager = FakeSessionUndo(UndoSessionResult(["u", "a"], "u", "a", 0, 0, 0))
    assert "失效记忆：0 条" in await PluginUndo(manager, lambda: None).undo("cli:1")


@pytest.mark.asyncio
async def test_setup_and_unload_register_one_command():
    ctx, commands = _context(FakeSessionUndo())
    await setup(ctx)
    assert commands.menu() == [("undo", "撤销上一轮对话")]
    await ctx.aclose()
    assert commands.menu() == [] and commands.handler("/undo") is None
