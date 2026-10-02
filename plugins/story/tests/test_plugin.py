"""Independent plugin setup and configuration contracts."""

from shiori_sdk.testing.service_context import FakeServiceContext
from shiori_sdk.rpc import Concurrency
from plugins.novelai.backend.plugin import setup as setup_novelai
from plugins.story.backend.plugin import setup


async def test_setup_uses_explicit_novelai_dependency_and_owns_draining(tmp_path):
    images = FakeServiceContext("novelai", tmp_path)
    await setup_novelai(images.as_capability())
    context = FakeServiceContext("story", tmp_path)
    context.dependencies.exports["novelai"] = images.exported
    await setup(context.as_capability())
    assert await context.rpc.handlers["list"]({}) == {"stories": []}
    assert context.rpc.concurrency["list"] == Concurrency.READ_ONLY
    assert len(context.runtime.drainers) == 1
    await context.runtime.drainers[0]()
    await context.aclose()
    await images.aclose()
    assert not context.rpc.handlers
