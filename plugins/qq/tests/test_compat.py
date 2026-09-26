"""NapCat 入站图片下载走注入的 HttpRequester（原宿主 http 迁移测试，#363 T5）。"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from core.net.http import HttpRequester, RequestBudget, RetryPolicy
from plugins.qq.backend.channel.compat import download_to_temp, extract_cq_images


def test_extract_cq_images_preserves_text_and_urls():
    assert extract_cq_images("hello [CQ:image,url=http://x/a.jpg]") == (
        "hello",
        ["http://x/a.jpg"],
    )


def _build_requester(handler) -> HttpRequester:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HttpRequester(
        client=client,
        retry_policy=RetryPolicy(max_attempts=1, base_delay_s=0.0, max_delay_s=0.0),
        default_timeout_s=1.0,
        default_budget=RequestBudget(total_timeout_s=2.0),
    )


@pytest.mark.asyncio
async def test_download_to_temp_uses_injected_requester(tmp_path: Path):
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            content=b"fake-image-bytes",
            headers={"content-type": "image/png"},
        )

    requester = _build_requester(_handler)
    try:
        paths = await download_to_temp(["https://example.com/image.png"], requester)
        assert len(paths) == 1
        path = Path(paths[0])
        assert path.suffix == ".png"
        assert path.read_bytes() == b"fake-image-bytes"
    finally:
        for raw_path in paths if "paths" in locals() else []:
            Path(raw_path).unlink(missing_ok=True)
        await requester.client.aclose()
