from __future__ import annotations

import base64
import html
import importlib
import logging
import re
from pathlib import Path

from core.net.http import HttpRequester, RequestBudget
from infra.channels.base import AttachmentStore

logger = logging.getLogger(__name__)

_CQ_IMAGE_RE = re.compile(r"\[CQ:image[^\]]*?(?:,|\b)url=([^,\]]+)[^\]]*\]")


def patch_ncatbot_ws_open_timeout(timeout_seconds: float) -> None:
    """覆盖 ncatbot 进程内写死的 1 秒 WebSocket 握手超时。"""
    if timeout_seconds <= 0:
        return
    try:
        adapter_mod = importlib.import_module("ncatbot.core.adapter.adapter")
        original_connect = getattr(
            adapter_mod, "_akashic_original_websockets_connect", None
        )
        if original_connect is None:
            original_connect = adapter_mod.websockets.connect
            adapter_mod._akashic_original_websockets_connect = original_connect

            def _patched_connect(*args, **kwargs):
                configured_timeout = getattr(
                    adapter_mod, "_akashic_websocket_open_timeout_seconds", None
                )
                if configured_timeout is not None:
                    kwargs["open_timeout"] = configured_timeout
                return adapter_mod._akashic_original_websockets_connect(*args, **kwargs)

            adapter_mod.websockets.connect = _patched_connect
        adapter_mod._akashic_websocket_open_timeout_seconds = timeout_seconds
    except Exception as exc:
        logger.warning(
            "[qq] patch ncatbot WebSocket open_timeout 失败，沿用 SDK 默认值: %s",
            exc,
        )


def extract_cq_images(raw: str) -> tuple[str, list[str]]:
    """从 CQ 码中提取图片 URL，返回纯文本和 URL 列表。"""
    urls = _CQ_IMAGE_RE.findall(raw)
    text = re.sub(r"\[CQ:image[^\]]*\]", "", raw).strip()
    return text, urls


async def download_to_temp(
    urls: list[str],
    requester: HttpRequester,
    attachments: AttachmentStore | None = None,
) -> list[str]:
    """Downloads inbound QQ images into the attachment store."""
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
                prefix="akashic_qq_",
                suffix=extension,
            )
            paths.append(str(path))
        except Exception as exc:
            logger.warning("[qq] 图片下载失败 url=%s 错误: %s", url[:80], exc)
    return paths


def is_local(path: str) -> bool:
    """Returns whether the value is a local path instead of a transport URI."""
    return not path.startswith(("http://", "https://", "base64://", "file://"))


def local_to_base64(path: str) -> str:
    """Encodes a local file as a NapCat base64 URI."""
    data = Path(path).read_bytes()
    return "base64://" + base64.b64encode(data).decode()
