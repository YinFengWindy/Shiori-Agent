from __future__ import annotations

from typing import Any

import httpx

from core.integrations.novelai.models import NovelAISettings
from core.net.http import HttpRequester


class NovelAIClient:
    """Thin HTTP client responsible for calling the upstream NovelAI API."""

    def __init__(self, requester: HttpRequester, settings: NovelAISettings) -> None:
        self._requester = requester
        self._settings = settings

    async def generate_image(
        self,
        *,
        action: str,
        prompt: str,
        model: str,
        parameters: dict[str, Any],
    ) -> httpx.Response:
        """Submit a NovelAI image generation request and return the raw response."""

        url = self._settings.base_url.rstrip("/") + "/ai/generate-image"
        return await self._requester.post(
            url,
            headers={
                "Authorization": f"Bearer {self._settings.token}",
                "Accept": "application/json, application/zip",
                "Content-Type": "application/json",
            },
            json={
                "input": prompt,
                "model": model,
                "action": action,
                "parameters": parameters,
            },
        )
