"""Lifecycle fake retains real module identity and withdraws contributions on close."""

from shiori_sdk.lifecycle import LifecycleFrame
from shiori_sdk.testing import FakeFrame, FakeLifecycle


class Module:
    slot = "test.export"

    async def run[FrameT: LifecycleFrame](self, frame: FrameT) -> FrameT:
        frame.slots["test:value"] = 42
        return frame


async def test_lifecycle_records_and_executes_the_registered_module() -> None:
    lifecycle = FakeLifecycle()
    module = Module()
    lifecycle.contribute("after_step", [module])
    registered = lifecycle.modules["after_step"]
    assert registered == [module]
    frame = FakeFrame()
    assert await registered[0].run(frame) is frame
    assert frame.slots == {"test:value": 42}
    lifecycle.close()
    assert lifecycle.modules == {}
