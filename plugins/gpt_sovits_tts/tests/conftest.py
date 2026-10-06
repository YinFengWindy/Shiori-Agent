"""SDK-only provider fixtures; no acoustic runtime or sibling plugin is installed."""

import io
import wave

import pytest
from shiori_sdk.testing.service_context import FakeServiceContext
from shiori_sdk.testing.services import FakePluginServices

from plugins.gpt_sovits_tts.backend.references import References
from plugins.gpt_sovits_tts.backend.settings import VoiceStore


class ProviderContext(FakeServiceContext):
    """Compose independent fake services for this provider's setup entry point."""

    def __init__(self, workspace):
        super().__init__("gpt_sovits_tts", workspace)
        self.services = FakePluginServices(self)


@pytest.fixture
def wav_bytes():
    def make(seconds=3, signal=1):
        stream = io.BytesIO()
        with wave.open(stream, "wb") as wav:
            wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            wav.writeframes(
                int(signal).to_bytes(2, "little", signed=True) * int(16000 * seconds)
            )
        return stream.getvalue()

    return make


@pytest.fixture
async def context(tmp_path):
    context = ProviderContext(tmp_path)
    context.roles.create_role(role_id="role", name="Role", system_prompt="Role")
    yield context
    await context.aclose()


@pytest.fixture
def references(tmp_path):
    return References(VoiceStore(tmp_path))


@pytest.fixture
def import_reference(tmp_path, references, wav_bytes):
    def add(seconds=3, signal=1):
        source = tmp_path / "private_runtime/imports/gpt_sovits_tts-audio/clip.wav"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(wav_bytes(seconds, signal))
        return references.import_file(tmp_path, str(source))["asset"]

    return add


@pytest.fixture
def configured(references, import_reference):
    asset = import_reference()
    references.store.save_role(
        "role",
        {"default": {"asset": asset, "prompt_text": "默认", "prompt_lang": "zh"}},
    )
    references.imported.clear()
    return references
