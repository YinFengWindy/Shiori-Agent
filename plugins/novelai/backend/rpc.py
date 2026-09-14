"""``plugin.novelai.*`` RPC handlers: manual generation, history and prompt tags.

Ports the desktop bridge's former ``novelai.*`` static methods (previously
``desktop_bridge.image_service.DesktopImageService`` /
``desktop_bridge.image_requests.DesktopImageRequestHandler``) onto the plugin
RPC capability (#177) so they live and die with the plugin: disabling
``novelai`` now makes every one of these methods disappear from the bridge,
where before they were wired unconditionally into ``DesktopBridgeService``.

Each handler matches the ``RpcHandler`` contract (``payload -> dict | None``);
registration and per-method concurrency lives in ``plugin.py``.
"""

from __future__ import annotations

from typing import Any


from .models import GenerateImageRequest
from .prompt_tags import PromptTagStore
from .service import NovelAIService
from .store import NovelAIStore


class NovelAIRpcHandlers:
    """Owns the request/response shaping for every ``plugin.novelai.*`` method."""

    def __init__(
        self,
        *,
        novelai_service: NovelAIService,
        novelai_store: NovelAIStore,
        prompt_tag_store: PromptTagStore,
        session_manager: Any,
        relationship_runtime: Any | None,
    ) -> None:
        self._service = novelai_service
        self._store = novelai_store
        self._prompt_tag_store = prompt_tag_store
        self._session_manager = session_manager
        self._relationship_runtime = relationship_runtime
        self._regenerating_message_media: set[tuple[str, str, int]] = set()

    async def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """``plugin.novelai.generate``: run one manual txt2img/img2img request."""

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
        result = await self._service.generate(request)
        return {"result": result.to_public_payload()}

    async def regenerate_message_media(self, payload: dict[str, Any]) -> dict[str, Any]:
        """``plugin.novelai.regenerateMessageMedia``: replace one message's image in place."""

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
            source = self._store.find_generation_source_by_output_path(current_path)
            if source is None:
                raise ValueError("当前图片不是 NovelAI 生成记录，无法重新生成")
            result = await self._service.regenerate(source, session_key=session_key)
            new_path = str(
                result.output_paths[0] if result.output_paths else ""
            ).strip()
            if not new_path:
                raise RuntimeError("NovelAI 重新生成未返回图片路径")
            session = await self._session_manager.replace_message_media(
                session_key=session_key,
                message_id=message_id,
                media_index=media_index,
                expected_path=current_path,
                new_path=new_path,
            )
        finally:
            self._regenerating_message_media.discard(target)
        presenter = self._presenter()
        message = next(
            item for item in session.messages if str(item.get("id") or "") == message_id
        )
        return {
            "result": result.to_public_payload(),
            "session": presenter.serialize_summary(session),
            "message": presenter.serialize_message(message),
        }

    async def history(self, payload: dict[str, Any]) -> dict[str, Any]:
        """``plugin.novelai.history``: recent generation records for one role."""

        limit = int(payload.get("limit") or 20)
        role_id = self._role_id(payload)
        return {"records": self._store.list_records(limit=limit, role_id=role_id)}

    async def prompt_tags_list(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """``plugin.novelai.prompt_tags.list``: the editable prompt-tag catalog."""

        return {
            "entries": [
                entry.to_dict() for entry in self._prompt_tag_store.list_entries()
            ]
        }

    async def prompt_tags_upsert(self, payload: dict[str, Any]) -> dict[str, Any]:
        """``plugin.novelai.prompt_tags.upsert``: validate and save one entry."""

        return {"entry": self._prompt_tag_store.upsert(payload).to_dict()}

    async def prompt_tags_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        """``plugin.novelai.prompt_tags.delete``: delete one entry."""

        self._prompt_tag_store.delete(str(payload.get("id") or ""))
        return {}

    def _presenter(self) -> Any:
        # Lazy import: keeps the plugin's module-load path from pulling in the
        # full desktop bridge dependency chain when the plugin loads outside a
        # desktop bridge process (mirrors the same discipline already applied
        # by agent.plugin_host.capabilities.RpcCapability for method_policy).
        from desktop_bridge.session_presenter import DesktopSessionPresenter

        return DesktopSessionPresenter(None, self._relationship_runtime)

    def _role_id(self, payload: dict[str, Any]) -> str:
        return str(payload.get("role_id") or "").strip()

    def _session_key(self, payload: dict[str, Any]) -> str:
        session_key = str(payload.get("session_key") or "").strip()
        role_id = self._role_id(payload)
        if session_key or not role_id:
            return session_key
        return str(self._session_manager.role_session_key(role_id))
