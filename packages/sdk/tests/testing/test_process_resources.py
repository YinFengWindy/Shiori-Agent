"""Independent SDK fixture exposes resource ownership without importing the host."""

from shiori_sdk.process_resources import PluginProcessResources
from shiori_sdk.testing.process_resources import FakeProcessResources


async def test_fake_resources_reuse_only_explicit_contract_and_close_once():
    class Resource:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True

    fake = FakeProcessResources()
    resources: PluginProcessResources = fake
    first = resources.acquire("tasks-v1", Resource)
    assert resources.acquire("tasks-v1", Resource) is first
    assert resources.acquire("other-v1", Resource) is not first
    await fake.close()
    assert first.closed and not resources.active
