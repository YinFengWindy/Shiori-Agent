"""Dynamic service SDK tests remain host independent."""

import pytest
from shiori_sdk.core.services import SERVICES
from shiori_sdk.testing import FakePluginContext
from shiori_sdk.testing.services import FakePluginServices


async def test_scope_cleanup_reclaims_published_handlers():
    context = FakePluginContext("neutral", inject=("services",))
    services = FakePluginServices(context)
    context.serve(SERVICES, services)

    async def echo(payload):
        return payload

    context.require(SERVICES).register(
        "echo", contract="neutral.v1", label="Neutral", methods={"run": echo}
    )
    assert await services.methods["echo", "run"]({"value": 42}) == {"value": 42}
    await context.aclose()
    assert services.entries == {}
    assert services.methods == {}
    with pytest.raises(RuntimeError, match="closed"):
        services.register(
            "late", contract="neutral.v1", label="Late", methods={"run": echo}
        )
