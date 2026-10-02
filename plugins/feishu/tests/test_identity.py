from __future__ import annotations

import httpx
import pytest
from shiori_sdk.testing.extensions import FakeConfig

from plugins.feishu.backend.config import FeishuAppConfig
from plugins.feishu.backend.identity import verify_app


def test_stored_secret_reference_resolves_without_rewriting_the_application():
    config = FakeConfig()
    config.references["${APP_SECRET}"] = " resolved "
    app = FeishuAppConfig(app_id="cli_a", app_secret="${APP_SECRET}")
    assert app.resolved_secret(config.resolve_reference) == "resolved"
    assert app.app_secret == "${APP_SECRET}"
    assert app.resolved_secret(FakeConfig().resolve_reference) == ""


@pytest.mark.asyncio
async def test_draft_verification_requires_real_bot_identity() -> None:
    async def response(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "token"})
        return httpx.Response(
            200,
            json={
                "code": 0,
                "bot": {"app_name": "A", "open_id": "ou_bot"},
            },
        )

    app = FeishuAppConfig(app_id="cli_a", app_secret="secret", domain="lark")
    assert await verify_app(
        app,
        resolver=FakeConfig().resolve_reference,
        transport=httpx.MockTransport(response),
    ) == {
        "name": "A",
        "open_id": "ou_bot",
    }

    async def denied(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": 10003, "msg": "bad credential"})

    with pytest.raises(Exception, match="10003"):
        await verify_app(
            app,
            resolver=FakeConfig().resolve_reference,
            transport=httpx.MockTransport(denied),
        )
