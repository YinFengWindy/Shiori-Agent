"""Speech SDK doubles obey explicit setup lifetime and transport contracts."""

import pytest
from shiori_sdk.testing.voice import FakeVoiceContext, FakeVoiceHttp
from shiori_sdk.voice import VoiceProviderInfo


async def test_fake_scope_revokes_provider_and_rejects_registration_after_close():
    context = FakeVoiceContext("speech")

    class Provider:
        info = VoiceProviderInfo("local", "Local")

    context.voice.register_tts(Provider())
    assert list(context.voice.tts) == ["local"]
    with pytest.raises(ValueError, match="Duplicate"):
        context.voice.register_tts(Provider())
    await context.aclose()
    assert context.voice.tts == {}
    with pytest.raises(RuntimeError, match="closed"):
        context.voice.register_tts(Provider())


def test_fake_transport_never_falls_back_to_a_real_network():
    fake = FakeVoiceHttp()
    with pytest.raises(AssertionError, match="No JSON"):
        fake.request_json("https://example.invalid", {}, b"")
    fake = FakeVoiceHttp(requester=lambda url, headers, body: {"result": body.decode()})
    assert fake.request_json("https://example.invalid", {}, b"fake") == {
        "result": "fake"
    }
