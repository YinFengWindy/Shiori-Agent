"""Independent plugin setup and configuration contracts."""

from pathlib import Path
from shiori_sdk.testing.service_context import FakeServiceContext
from shiori_sdk.rpc import Concurrency
from plugins.novelai.backend import plugin as novelai_plugin
from plugins.novelai.backend.plugin import setup as setup_novelai
from plugins.story.backend.plugin import setup

PACKAGE_DIR = Path(__file__).resolve().parents[1]
NOVELAI_PACKAGE_DIR = Path(novelai_plugin.__file__).resolve().parents[1]


async def test_setup_uses_explicit_novelai_dependency_and_owns_draining(tmp_path):
    images = FakeServiceContext("novelai", tmp_path, package_dir=NOVELAI_PACKAGE_DIR)
    await setup_novelai(images)
    context = FakeServiceContext("story", tmp_path, package_dir=PACKAGE_DIR)
    context.fake_dependencies.exports["novelai"] = images.exported
    await setup(context)
    assert await context.fake_rpc.handlers["list"]({}) == {"stories": []}
    assert context.fake_rpc.concurrency["list"] == Concurrency.READ_ONLY
    assert len(context.fake_runtime.drainers) == 1
    await context.fake_runtime.drainers[0]()
    await context.aclose()
    await images.aclose()
    assert not context.fake_rpc.handlers
