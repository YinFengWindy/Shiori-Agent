"""SDK-only provider fixtures and synthetic WAV data."""

import io
import wave
from pathlib import Path

import pytest
from shiori_sdk.core.services import SERVICES
from shiori_sdk.testing.service_context import FakeServiceContext
from shiori_sdk.testing.services import FakePluginServices

PACKAGE_DIR = Path(__file__).resolve().parents[1]


class ProviderContext(FakeServiceContext):
    """Assemble only the capabilities this independent provider needs."""

    def __init__(self, workspace):
        super().__init__("fish_audio", workspace, package_dir=PACKAGE_DIR)
        self.fake_services = FakePluginServices(self)
        self.serve(SERVICES, self.fake_services)


@pytest.fixture
async def context(tmp_path):
    context = ProviderContext(tmp_path)
    for role in ("alice", "bob"):
        context.fake_roles.create_role(role_id=role, name=role, system_prompt=role)
    yield context
    await context.aclose()


@pytest.fixture
def audio():
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        wav.writeframes(b"\x01\x00" * 1600)
    return stream.getvalue()
