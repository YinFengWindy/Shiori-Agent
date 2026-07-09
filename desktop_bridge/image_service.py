from __future__ import annotations

from typing import Any

from core.integrations.novelai import NovelAIService, NovelAIStore
from core.integrations.novelai.models import GenerateImageRequest
from core.roles import RoleAggregateService


class DesktopImageService:
    """Desktop-facing wrapper around NovelAI generation and history use cases."""

    def __init__(
        self,
        *,
        role_service: RoleAggregateService,
        novelai_service: NovelAIService | None,
        novelai_store: NovelAIStore,
    ) -> None:
        self._role_service = role_service
        self._novelai_service = novelai_service
        self._novelai_store = novelai_store

    async def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._novelai_service is None:
            raise ValueError("NovelAI 未配置")
        request = GenerateImageRequest(
            prompt=str(payload.get("prompt") or ""),
            mode=str(payload.get("mode") or "txt2img"),  # type: ignore[arg-type]
            base_image_path=str(payload.get("base_image_path") or ""),
            strength=(
                float(payload["strength"])
                if payload.get("strength") is not None
                else None
            ),
            noise=(
                float(payload["noise"])
                if payload.get("noise") is not None
                else None
            ),
            negative_prompt=str(payload.get("negative_prompt") or ""),
            size_preset=str(payload.get("size_preset") or "square"),  # type: ignore[arg-type]
            custom_width=(
                int(payload["custom_width"])
                if payload.get("custom_width") is not None
                else None
            ),
            custom_height=(
                int(payload["custom_height"])
                if payload.get("custom_height") is not None
                else None
            ),
            steps=(
                int(payload["steps"])
                if payload.get("steps") is not None
                else None
            ),
            seed=(
                int(payload["seed"])
                if payload.get("seed") is not None
                else None
            ),
            sampler=str(payload.get("sampler") or "k_euler"),
            model=str(payload.get("model") or ""),
            role_id=self._role_id(payload),
            session_key=self._session_key(payload),
        )
        result = await self._novelai_service.generate(request)
        return result.to_public_payload()

    def history(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        limit = int(payload.get("limit") or 20)
        role_id = self._role_id(payload)
        return self._novelai_store.list_records(limit=limit, role_id=role_id)

    def _role_id(self, payload: dict[str, Any]) -> str:
        return str(payload.get("role_id") or "").strip()

    def _session_key(self, payload: dict[str, Any]) -> str:
        session_key = str(payload.get("session_key") or "").strip()
        role_id = self._role_id(payload)
        if session_key or not role_id:
            return session_key
        return self._role_service.sessions.derive_session_key(role_id)
