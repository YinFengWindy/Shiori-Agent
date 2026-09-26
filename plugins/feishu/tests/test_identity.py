from __future__ import annotations

import httpx
import pytest

from plugins.feishu.backend.config import FeishuAppConfig
from plugins.feishu.backend.identity import verify_app


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
    assert await verify_app(app, transport=httpx.MockTransport(response)) == {
        "name": "A",
        "open_id": "ou_bot",
    }

    async def denied(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": 10003, "msg": "bad credential"})

    with pytest.raises(Exception, match="10003"):
        await verify_app(app, transport=httpx.MockTransport(denied))
