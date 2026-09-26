from __future__ import annotations

from collections.abc import Awaitable, Callable
import inspect
from typing import Any

from core.roles import RoleAggregateService

from .role_presenter import DesktopRolePresenter
from .voice.voice_handler import DesktopVoiceHandler


class DesktopRoleRequestHandler:
    """Handles role bridge requests.

    No longer "role-owned pet" or role differences: both moved to the plugins
    that own them (#181-D and #236 respectively), each leaving this router to
    answer `None` so the plugin RPC dispatcher downstream picks the method up.
    """

    def __init__(
        self,
        *,
        role_service: RoleAggregateService,
        role_presenter: DesktopRolePresenter,
        voice_handler: DesktopVoiceHandler,
        card_import_service: Any | None = None,
        publish_event: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self._role_service = role_service
        self._role_presenter = role_presenter
        self._voice_handler = voice_handler
        self._card_import_service = card_import_service
        self._publish_event = publish_event

    async def handle(
        self, method: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        if method == "roles.list":
            return {
                "roles": [
                    self._role_presenter.serialize(role)
                    for role in self._role_service.repository.list_roles()
                ]
            }
        if method == "roles.create":
            aggregate = await self._role_service.create_role_async(
                role_id=str(payload.get("role_id") or "").strip() or None,
                name=str(payload.get("name") or ""),
                description=str(payload.get("description") or ""),
                system_prompt=str(payload.get("system_prompt") or ""),
                background=str(payload.get("background") or ""),
                profile=self._dict_payload(payload, "profile"),
                runtime_config=self._dict_payload(payload, "runtime_config"),
                avatar_source=str(payload.get("avatar_source") or "").strip() or None,
                illustration_sources=self._string_list_payload(
                    payload, "illustration_sources"
                ),
            )
            return {"role": self._role_presenter.serialize(aggregate.role)}
        if method in {
            "roles.cardImport.preview",
            "roles.cardImport.commit",
            "roles.cardImport.cancel",
        }:
            service = self._card_import_service
            if service is None:
                raise RuntimeError("role card import service unavailable")
            operation = {
                "roles.cardImport.preview": "preview",
                "roles.cardImport.commit": "commit",
                "roles.cardImport.cancel": "cancel",
            }[method]
            handler = getattr(service, operation, None)
            if not callable(handler):
                raise RuntimeError(
                    f"role card import service lacks {operation} operation"
                )
            argument = dict(payload)
            result = handler(argument)
            if inspect.isawaitable(result):
                result = await result
            if hasattr(result, "to_dict") and callable(result.to_dict):
                result = result.to_dict()
            if not isinstance(result, dict):
                raise RuntimeError(
                    f"role card import {operation} returned invalid payload"
                )
            if operation == "commit":
                role = result.get("role")
                role_id = (
                    str(role.get("id") or "").strip() if isinstance(role, dict) else ""
                )
                if not role_id:
                    raise RuntimeError("role card import commit returned no role")
                result = {
                    **result,
                    "role": self._role_presenter.serialize(
                        self._role_service.repository.get_required(role_id)
                    ),
                }
            return result
        if method == "roles.update":
            if "channel_bindings" in payload:
                raise ValueError("角色渠道绑定已迁移到账号归属与响应规则")
            role_id = str(payload.get("role_id") or "")
            previous = self._role_service.repository.get_required(role_id)
            update_kwargs: dict[str, Any] = {
                "name": payload.get("name"),
                "description": payload.get("description"),
                "system_prompt": payload.get("system_prompt"),
                "background": payload.get("background"),
                "runtime_config": self._dict_payload(payload, "runtime_config"),
            }
            if "profile" in payload:
                update_kwargs["profile"] = self._merge_profile_payload(
                    previous.profile.to_dict(),
                    self._dict_payload(payload, "profile"),
                )
            aggregate = await self._role_service.update_role_async(
                role_id,
                **update_kwargs,
                proactive=self._dict_payload(payload, "proactive"),
                avatar_source=str(payload.get("avatar_source") or "").strip() or None,
                avatar_asset=str(payload.get("avatar_asset") or "").strip() or None,
                chat_background=str(payload.get("chat_background") or "").strip()
                or None,
                clear_chat_background=bool(payload.get("clear_chat_background")),
                clear_avatar=bool(payload.get("clear_avatar")),
                illustration_sources=self._string_list_payload(
                    payload, "illustration_sources"
                ),
                illustration_category_id=(
                    str(payload.get("illustration_category_id") or "").strip() or None
                ),
                removed_illustrations=self._string_list_payload(
                    payload, "removed_illustrations"
                ),
                clear_illustrations=bool(payload.get("clear_illustrations")),
                asset_categories=self._dict_list_payload(payload, "asset_categories"),
                asset_category_bindings=self._string_dict_payload(
                    payload, "asset_category_bindings"
                ),
                plugin_drafts=self._dict_payload(payload, "plugin_drafts"),
            )
            await self._voice_handler.reconcile_role_update(
                dict(previous.runtime_config),
                aggregate.role.runtime_config,
            )
            return {"role": self._role_presenter.serialize(aggregate.role)}
        if method == "roles.delete":
            role_id = str(payload.get("role_id") or "").strip()
            role = self._role_service.repository.get_required(role_id)
            deleted, session_deleted = self._role_service.delete_role(role_id)
            if deleted:
                await self._voice_handler.retire_deleted_role(role.runtime_config)
            return {"deleted": deleted, "session_deleted": session_deleted}
        # `roles.pets.import` / `.remove` / `.select` used to live here. They are
        # now `plugin.desktop_pet.pets.*`, registered by the plugin that owns
        # them (#181-D), so the core bridge no longer knows what a pet package
        # is — and the desktop's package manager, which is now plugin UI, can
        # only reach its own namespace anyway.
        return None

    @staticmethod
    def _dict_payload(payload: dict[str, Any], key: str) -> dict[str, Any] | None:
        value = payload.get(key)
        return dict(value) if isinstance(value, dict) else None

    @staticmethod
    def _merge_profile_payload(
        current: dict[str, Any], patch: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Applies one bridge profile patch without discarding unrelated role fields."""
        if patch is None:
            return dict(current)
        merged = dict(current)
        for key, value in patch.items():
            existing = merged.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                merged[key] = {**existing, **value}
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _list_payload(payload: dict[str, Any], key: str) -> list[Any] | None:
        value = payload.get(key)
        return list(value) if isinstance(value, list) else None

    @staticmethod
    def _string_list_payload(payload: dict[str, Any], key: str) -> list[str] | None:
        value = payload.get(key)
        if not isinstance(value, list):
            return None
        return [str(item) for item in value if str(item).strip()]

    @staticmethod
    def _dict_list_payload(
        payload: dict[str, Any], key: str
    ) -> list[dict[str, Any]] | None:
        value = payload.get(key)
        if not isinstance(value, list):
            return None
        return [dict(item) for item in value if isinstance(item, dict)]

    @staticmethod
    def _string_dict_payload(
        payload: dict[str, Any], key: str
    ) -> dict[str, str] | None:
        value = payload.get(key)
        if not isinstance(value, dict):
            return None
        return {str(path): str(category_id) for path, category_id in value.items()}
