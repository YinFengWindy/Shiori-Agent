"""Provider setup and disposal through the SDK-only context."""

from shiori_sdk.testing.voice import FakeVoiceContext
from plugins.tencent_asr.backend.plugin import setup


async def test_setup_registers_only_its_slot_and_disposal_revokes_it():
    ctx = FakeVoiceContext("tencent_asr")
    await setup(ctx.as_capability())
    assert list(ctx.voice.asr) == ["tencent"]
    assert ctx.voice.tts == {}
    await ctx.aclose()
    assert ctx.voice.asr == {}
