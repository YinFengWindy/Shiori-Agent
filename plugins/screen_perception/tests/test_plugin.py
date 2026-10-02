"""Independent plugin setup and configuration contracts."""

from shiori_sdk.testing.service_context import FakeServiceContext
from plugins.screen_perception.backend.plugin import setup


async def test_setup_registers_read_only_observation_and_disposes_it(tmp_path):
    context = FakeServiceContext("screen_perception", tmp_path)
    await setup(context.as_capability())
    assert context.tools.get_tool("observe_screen") is not None
    assert context.tools.options["observe_screen"]["risk"] == "read-only"
    await context.aclose()
    assert not context.tools.tools
