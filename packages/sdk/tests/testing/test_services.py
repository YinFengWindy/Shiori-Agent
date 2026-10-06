"""Dynamic service SDK tests remain host independent."""

import pytest
from shiori_sdk.testing.services import FakeServiceProviderContext


async def test_scope_cleanup_reclaims_published_handlers():
    context = FakeServiceProviderContext("neutral")

    async def echo(payload):
        return payload

    context.as_capability().services.register(
        "echo", contract="neutral.v1", label="Neutral", methods={"run": echo}
    )
    assert await context.services.methods["echo", "run"]({"value": 42}) == {"value": 42}
    await context.aclose()
    assert context.services.entries == {}
    assert context.services.methods == {}
    with pytest.raises(RuntimeError, match="closed"):
        context.services.register(
            "late", contract="neutral.v1", label="Late", methods={"run": echo}
        )
