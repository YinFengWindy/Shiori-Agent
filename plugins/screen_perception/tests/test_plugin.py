"""Independent plugin setup and configuration contracts."""

from pathlib import Path
from shiori_sdk.testing.service_context import FakeServiceContext
from plugins.screen_perception.backend.plugin import setup

PACKAGE_DIR = Path(__file__).resolve().parents[1]


async def test_setup_registers_read_only_observation_and_disposes_it(tmp_path):
    context = FakeServiceContext("screen_perception", tmp_path, package_dir=PACKAGE_DIR)
    await setup(context)
    assert context.fake_tools.get_tool("observe_screen") is not None
    assert context.fake_tools.options["observe_screen"]["risk"] == "read-only"
    await context.aclose()
    assert not context.fake_tools.tools
