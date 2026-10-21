from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from bus.event_bus import EventBus
from shiori_sdk.lifecycle import ResponseMetadata
from agent.lifecycle.facade import TurnLifecycle
from agent.lifecycle.phase import Phase, PhaseFrame, topo_sort_modules
from agent.lifecycle.types import BeforeReasoningCtx, BeforeStepCtx, BeforeTurnCtx
from shiori_sdk.lifecycle import AfterReasoningCtx, AfterStepCtx, AfterTurnCtx


@dataclass
class _TextFrame(PhaseFrame[str, str]):
    pass


class _SetupModule:
    produces = ("text:value",)

    async def run(self, frame: _TextFrame) -> _TextFrame:
        frame.slots["text:value"] = f"setup_{frame.input}"
        return frame


class _MutateModule:
    requires = ("text:value",)
    produces = ("text:value",)

    async def run(self, frame: _TextFrame) -> _TextFrame:
        frame.slots["text:value"] = f"{frame.slots['text:value']}_mutated"
        return frame


class _FinalizeModule:
    requires = ("text:value",)

    async def run(self, frame: _TextFrame) -> _TextFrame:
        frame.output = f"{frame.slots['text:value']}_finalized"
        return frame


class _FailingModule:
    async def run(self, frame: _TextFrame) -> _TextFrame:
        raise RuntimeError("setup failed")


class _NoOutputModule:
    async def run(self, frame: _TextFrame) -> _TextFrame:
        return frame


class _NeedsMissingSlotModule:
    requires = ("missing:value",)

    async def run(self, frame: _TextFrame) -> _TextFrame:
        frame.output = str(frame.slots["missing:value"])
        return frame


class _NeedsMissingModuleSlotModule:
    slot = "plugin.consumer"
    requires = ("plugin.provider",)

    async def run(self, frame: _TextFrame) -> _TextFrame:
        frame.output = "disabled module ran"
        return frame


class _PassThroughFinalizeModule:
    async def run(self, frame: _TextFrame) -> _TextFrame:
        frame.output = frame.input
        return frame


class _NeedsDisabledModuleSlotModule:
    slot = "plugin.after_consumer"
    requires = ("plugin.consumer",)

    async def run(self, frame: _TextFrame) -> _TextFrame:
        frame.output = "dependent module ran"
        return frame


@pytest.mark.asyncio
async def test_phase_modules_run_in_order():
    phase = Phase[str, str, _TextFrame](
        [_SetupModule(), _MutateModule(), _FinalizeModule()],
        frame_factory=_TextFrame,
    )
    result = await phase.run("hello")
    assert result == "setup_hello_mutated_finalized"


@pytest.mark.asyncio
async def test_phase_modules_can_passthrough():
    phase = Phase[str, str, _TextFrame](
        [_SetupModule(), _FinalizeModule()],
        frame_factory=_TextFrame,
    )
    result = await phase.run("hello")
    assert result == "setup_hello_finalized"


@pytest.mark.asyncio
async def test_phase_module_exception_propagates():
    phase = Phase[str, str, _TextFrame]([_FailingModule()], frame_factory=_TextFrame)
    with pytest.raises(RuntimeError, match="setup failed"):
        await phase.run("x")


@pytest.mark.asyncio
async def test_phase_requires_output():
    phase = Phase[str, str, _TextFrame]([_NoOutputModule()], frame_factory=_TextFrame)
    with pytest.raises(RuntimeError, match="Phase 模块链未产生 output"):
        await phase.run("x")


def test_phase_warns_when_slot_not_closed(caplog: pytest.LogCaptureFixture):
    with caplog.at_level("WARNING", logger="agent.lifecycle.phase"):
        Phase[str, str, _TextFrame](
            [_NeedsMissingSlotModule()],
            frame_factory=_TextFrame,
        )
    assert "Phase slot 未闭合" in caplog.text


def test_phase_warns_when_module_dependency_missing(
    caplog: pytest.LogCaptureFixture,
):
    with caplog.at_level("WARNING", logger="agent.lifecycle.phase"):
        Phase[str, str, _TextFrame](
            [_NeedsMissingModuleSlotModule()],
            frame_factory=_TextFrame,
        )
    assert "Phase 模块依赖不存在" in caplog.text
    assert "Phase slot 未闭合" not in caplog.text


@pytest.mark.asyncio
async def test_phase_disables_module_with_missing_module_dependency(
    caplog: pytest.LogCaptureFixture,
):
    with caplog.at_level("WARNING", logger="agent.lifecycle.phase"):
        phase = Phase[str, str, _TextFrame](
            [_NeedsMissingModuleSlotModule(), _PassThroughFinalizeModule()],
            frame_factory=_TextFrame,
        )
    result = await phase.run("hello")
    assert result == "hello"
    assert "已禁用模块" in caplog.text


def test_topo_sort_disables_missing_module_dependency_recursively(
    caplog: pytest.LogCaptureFixture,
):
    with caplog.at_level("WARNING", logger="agent.lifecycle.phase"):
        modules = topo_sort_modules(
            [
                _NeedsMissingModuleSlotModule(),
                _NeedsDisabledModuleSlotModule(),
            ]
        )
    assert modules == []
    assert "plugin.consumer" in caplog.text
    assert "plugin.after_consumer" in caplog.text


_now = datetime.now()


def _before_turn_ctx(**kwargs: object) -> BeforeTurnCtx:
    return BeforeTurnCtx(
        session_key="k",
        channel="c",
        chat_id="ch",
        content="hello",
        timestamp=_now,
        retrieved_memory_block="",
        retrieval_trace_raw=None,
        history_messages=(),
        context_scope=None,
    )


@pytest.mark.asyncio
async def test_lifecycle_hooks_receive_only_their_own_phase():
    """Each facade registration is the bus subscription for that phase only."""
    bus = EventBus()
    lifecycle = TurnLifecycle(bus)
    handlers = {
        name: AsyncMock(return_value=None)
        for name in (
            "before_turn",
            "before_reasoning",
            "before_step",
            "after_reasoning",
            "after_step",
            "after_turn",
        )
    }
    lifecycle.on_before_turn(handlers["before_turn"])
    lifecycle.on_before_reasoning(handlers["before_reasoning"])
    lifecycle.on_before_step(handlers["before_step"])
    lifecycle.on_after_reasoning(handlers["after_reasoning"])
    lifecycle.on_after_step(handlers["after_step"])
    lifecycle.on_after_turn(handlers["after_turn"])

    await bus.emit(_before_turn_ctx())
    await bus.emit(
        BeforeReasoningCtx(
            session_key="k",
            channel="c",
            chat_id="ch",
            content="hello",
            timestamp=_now,
            skill_names=[],
            retrieved_memory_block="",
        )
    )
    await bus.emit(
        BeforeStepCtx(
            session_key="k",
            channel="c",
            chat_id="ch",
            iteration=0,
            input_tokens_estimate=100,
            visible_tool_names=None,
        )
    )
    await bus.emit(
        AfterReasoningCtx(
            session_key="k",
            channel="c",
            chat_id="ch",
            tools_used=(),
            thinking=None,
            response_metadata=ResponseMetadata(raw_text=""),
            streamed=False,
            tool_chain=(),
            context_retry={},
            reply="hi",
        )
    )
    await bus.fanout(
        AfterStepCtx(
            session_key="k",
            channel="c",
            chat_id="ch",
            iteration=0,
            context_tokens_estimate=0,
            tools_called=(),
            partial_reply="",
            tools_used_so_far=(),
            tool_chain_partial=(),
            partial_thinking=None,
            has_more=True,
        )
    )
    await bus.fanout(
        AfterTurnCtx(
            session_key="k",
            channel="c",
            chat_id="ch",
            reply="hi",
            tools_used=(),
            thinking=None,
            will_dispatch=True,
        )
    )

    for handler in handlers.values():
        handler.assert_awaited_once()
