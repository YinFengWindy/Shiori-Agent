"""Inbound CQ image extraction and attachment storage for QQ accounts."""

from __future__ import annotations

import html
import logging
import re

from core.net.http import HttpRequester, RequestBudget
from infra.channels.base import AttachmentStore

logger = logging.getLogger(__name__)

_CQ_IMAGE_RE = re.compile(r"\[CQ:image[^\]]*?(?:,|\b)url=([^,\]]+)[^\]]*\]")


def extract_cq_images(raw: str) -> tuple[str, list[str]]:
    """Extract image URLs from CQ codes and return the remaining text."""
    urls = _CQ_IMAGE_RE.findall(raw)
    text = re.sub(r"\[CQ:image[^\]]*\]", "", raw).strip()
    return text, urls


async def download_to_temp(
    urls: list[str],
    requester: HttpRequester,
    attachments: AttachmentStore | None = None,
) -> list[str]:
    """Download inbound QQ images into the attachment store."""
    if not urls:
        return []
    paths: list[str] = []
    attachment_store = attachments or AttachmentStore()
    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }
    for url in urls:
        try:
            url = html.unescape(url)
            response = await requester.get(
                url,
                follow_redirects=True,
                timeout_s=15.0,
                budget=RequestBudget(total_timeout_s=20.0),
            )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "image/jpeg")
            extension = ext_map.get(content_type.split(";")[0].strip(), ".jpg")
            path = attachment_store.write_bytes(
                response.content,
                prefix="shiori_qq_",
                suffix=extension,
            )
            paths.append(str(path))
        except Exception as exc:
            logger.warning("[qq] 图片下载失败 url=%s 错误: %s", url[:80], exc)
    return paths
