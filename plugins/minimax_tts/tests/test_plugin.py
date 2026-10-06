"""Provider setup and disposal through the SDK-only context."""

from shiori_sdk.testing.voice import FakeVoiceContext
from plugins.minimax_tts.backend.plugin import setup


async def test_setup_registers_only_its_slot_and_disposal_revokes_it():
    ctx = FakeVoiceContext("minimax_tts")
    await setup(ctx.as_capability())
    assert list(ctx.voice.tts) == ["minimax"]
    assert ctx.voice.asr == {}
    await ctx.aclose()
    assert ctx.voice.tts == {}
