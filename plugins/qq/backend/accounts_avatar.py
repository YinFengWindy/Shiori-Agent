"""QQ account avatars fetched from the public QQ avatar service."""

from __future__ import annotations

import logging

import httpx

from core.accounts import avatar_data_uri
from core.net.http import shared_ssl_context

logger = logging.getLogger(__name__)

QQ_AVATAR_URL = "https://q1.qlogo.cn/g?b=qq&nk={uin}&s=100"


async def fetch_qq_avatar(
    uin: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> str | None:
    """The QQ number's 100px avatar as a data URI; None when it cannot be fetched.

    A network boundary: failures are logged, never raised, so a connection
    never fails because of its avatar.
    """
    try:
        async with httpx.AsyncClient(
            timeout=10.0, transport=transport, verify=shared_ssl_context()
        ) as client:
            response = await client.get(
                QQ_AVATAR_URL.format(uin=uin), follow_redirects=True
            )
            response.raise_for_status()
        return avatar_data_uri(response.content)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("[qq] 账号 %s 头像获取失败: %s", uin, exc)
        return None
