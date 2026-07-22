from __future__ import annotations

from typing import Any

from core.integrations.novelai import NovelAIService, NovelAIStore, PromptTagStore
from core.integrations.novelai.models import GenerateImageRequest
from core.roles import RoleAggregateService
from session.manager import Session, SessionManager


class DesktopImageService:
    """Desktop-facing wrapper around NovelAI generation and history use cases."""

    def __init__(
        self,
        *,
        role_service: RoleAggregateService,
        novelai_service: NovelAIService | None,
        novelai_store: NovelAIStore,
        prompt_tag_store: PromptTagStore | None = None,
        session_manager: SessionManager | None = None,
    ) -> None:
        self._role_service = role_service
        self._session_manager = session_manager
        self._novelai_service = novelai_service
        self._novelai_store = novelai_store
        self._prompt_tag_store = prompt_tag_store
        self._regenerating_message_media: set[tuple[str, str, int]] = set()

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
                float(payload["noise"]) if payload.get("noise") is not None else None
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
            steps=(int(payload["steps"]) if payload.get("steps") is not None else None),
            seed=(int(payload["seed"]) if payload.get("seed") is not None else None),
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

    async def regenerate_message_media(
        self,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], Session]:
        """Regenerate one NovelAI-backed desktop message image in place."""

        if self._novelai_service is None:
            raise ValueError("NovelAI 未配置")
        if self._session_manager is None:
            raise RuntimeError("桌面图片重生缺少 SessionManager")
        session_key = str(payload.get("session_key") or "").strip()
        message_id = str(payload.get("message_id") or "").strip()
        raw_media_index = payload.get("media_index")
        if not session_key or not message_id or raw_media_index is None:
            raise ValueError("session_key、message_id 和 media_index 不能为空")
        media_index = int(raw_media_index)
        target = (session_key, message_id, media_index)
        if target in self._regenerating_message_media:
            raise ValueError("这张图片正在重新生成")
        self._regenerating_message_media.add(target)
        try:
            current_path = self._session_manager.get_message_media(
                session_key=session_key,
                message_id=message_id,
                media_index=media_index,
            )
            source = self._novelai_store.find_generation_source_by_output_path(
                current_path
            )
            if source is None:
                raise ValueError("当前图片不是 NovelAI 生成记录，无法重新生成")
            result = await self._novelai_service.regenerate(
                source,
                session_key=session_key,
            )
            new_path = str(result.output_paths[0] if result.output_paths else "").strip()
            if not new_path:
                raise RuntimeError("NovelAI 重新生成未返回图片路径")
            session = await self._session_manager.replace_message_media(
                session_key=session_key,
                message_id=message_id,
                media_index=media_index,
                expected_path=current_path,
                new_path=new_path,
            )
            return result.to_public_payload(), session
        finally:
            self._regenerating_message_media.discard(target)

    def prompt_tags_list(self) -> list[dict[str, Any]]:
        """Return the editable prompt-tag catalog."""

        store = self._require_prompt_tag_store()
        return [entry.to_dict() for entry in store.list_entries()]

    def prompt_tags_upsert(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate and save one prompt-tag entry."""

        return self._require_prompt_tag_store().upsert(payload).to_dict()

    def prompt_tags_delete(self, payload: dict[str, Any]) -> None:
        """Delete one prompt-tag entry."""

        self._require_prompt_tag_store().delete(str(payload.get("id") or ""))

    def _require_prompt_tag_store(self) -> PromptTagStore:
        if self._prompt_tag_store is None:
            raise RuntimeError("提示词 tag 知识库未配置")
        return self._prompt_tag_store

    def _role_id(self, payload: dict[str, Any]) -> str:
        return str(payload.get("role_id") or "").strip()

    def _session_key(self, payload: dict[str, Any]) -> str:
        session_key = str(payload.get("session_key") or "").strip()
        role_id = self._role_id(payload)
        if session_key or not role_id:
            return session_key
        return self._role_service.sessions.derive_session_key(role_id)
