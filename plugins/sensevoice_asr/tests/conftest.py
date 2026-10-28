"""Independent SDK-only fixtures with tiny generated WAV recordings."""

import io
import wave
from pathlib import Path

import pytest
from shiori_sdk.testing.service_context import FakeServiceContext
from shiori_sdk.testing.services import FakePluginServices

PACKAGE_DIR = Path(__file__).resolve().parents[1]


class ProviderContext(FakeServiceContext):
    """Compose the explicit public-service fixture with ordinary plugin capabilities."""

    def __init__(self, workspace):
        super().__init__("sensevoice_asr", workspace, package_dir=PACKAGE_DIR)
        self.services = FakePluginServices(self)


@pytest.fixture
def audio():
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        wav.writeframes(b"\x01\x00" * 1600)
    return stream.getvalue()


@pytest.fixture
async def context(tmp_path):
    context = ProviderContext(tmp_path)
    yield context
    await context.aclose()
