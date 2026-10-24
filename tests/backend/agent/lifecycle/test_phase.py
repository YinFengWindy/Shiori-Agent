from __future__ import annotations

from dataclasses import dataclass

import pytest

from agent.lifecycle.phase import Phase, PhaseFrame


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
