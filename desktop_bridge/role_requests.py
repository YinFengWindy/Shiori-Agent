from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from core.roles import RoleAggregateService, RolePetPackageService, RoleStore

from .role_presenter import DesktopRolePresenter
from .role_difference_service import RoleDifferenceGenerationService
from .voice_handler import DesktopVoiceHandler


class DesktopRoleRequestHandler:
    """Handles role and role-owned pet bridge requests."""

    def __init__(
        self,
        *,
        role_service: RoleAggregateService,
        role_store: RoleStore,
        pet_packages: RolePetPackageService,
        role_differences: RoleDifferenceGenerationService,
        role_presenter: DesktopRolePresenter,
        voice_handler: DesktopVoiceHandler,
        publish_event: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self._role_service = role_service
        self._role_store = role_store
        self._pet_packages = pet_packages
        self._role_differences = role_differences
        self._role_presenter = role_presenter
        self._voice_handler = voice_handler
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
                runtime_config=self._dict_payload(payload, "runtime_config"),
                avatar_source=str(payload.get("avatar_source") or "").strip() or None,
                illustration_sources=self._string_list_payload(
                    payload, "illustration_sources"
                ),
            )
            return {"role": self._role_presenter.serialize(aggregate.role)}
        if method == "roles.update":
            role_id = str(payload.get("role_id") or "")
            previous = self._role_service.repository.get_required(role_id)
            aggregate = await self._role_service.update_role_async(
                role_id,
                name=payload.get("name"),
                description=payload.get("description"),
                system_prompt=payload.get("system_prompt"),
                background=payload.get("background"),
                runtime_config=self._dict_payload(payload, "runtime_config"),
                channel_bindings=self._list_payload(payload, "channel_bindings"),
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
                desktop_pet_enabled=(
                    bool(payload["desktop_pet_enabled"])
                    if isinstance(payload.get("desktop_pet_enabled"), bool)
                    else None
                ),
            )
            await self._voice_handler.reconcile_role_update(
                dict(previous.runtime_config),
                aggregate.role.runtime_config,
            )
            return {"role": self._role_presenter.serialize(aggregate.role)}
        if method == "roles.differences.generate":
            result = await self._role_differences.generate(
                role_id=str(payload.get("role_id") or ""),
                base_asset=str(payload.get("base_asset") or ""),
                emit_progress=self._emit_difference_progress,
            )
            self._role_service.sessions.open_by_role(result["role"])
            return {
                "job_id": result["job_id"],
                "category_id": result["category_id"],
                "category_name": result["category_name"],
                "role": self._role_presenter.serialize(result["role"]),
            }
        if method == "roles.delete":
            role_id = str(payload.get("role_id") or "").strip()
            role = self._role_service.repository.get_required(role_id)
            deleted, session_deleted = self._role_service.delete_role(role_id)
            if deleted:
                await self._voice_handler.retire_deleted_role(role.runtime_config)
            return {"deleted": deleted, "session_deleted": session_deleted}
        if method == "roles.pets.import":
            role_id = str(payload.get("role_id") or "").strip()
            package = self._pet_packages.import_package(
                role_id,
                str(payload.get("source") or "").strip(),
            )
            role = self._role_store.get_role(role_id)
            if role is None:
                raise KeyError(f"role 不存在: {role_id}")
            return {
                "package": package.to_dict(),
                "role": self._role_presenter.serialize(role),
            }
        if method == "roles.pets.remove":
            role_id = str(payload.get("role_id") or "").strip()
            self._pet_packages.remove_package(
                role_id,
                str(payload.get("package_id") or "").strip(),
            )
            role = self._role_store.get_role(role_id)
            if role is None:
                raise KeyError(f"role 不存在: {role_id}")
            return {"role": self._role_presenter.serialize(role)}
        if method == "roles.pets.select":
            role = self._pet_packages.select_package(
                str(payload.get("role_id") or "").strip(),
                str(payload.get("package_id") or "").strip(),
            )
            return {"role": self._role_presenter.serialize(role)}
        return None

    async def _emit_difference_progress(self, payload: dict[str, Any]) -> None:
        await self._publish_event(
            {
                "id": str(payload.get("job_id") or "role-differences"),
                "type": "event",
                "method": "roles.differences.progress",
                "payload": payload,
            }
        )

    @staticmethod
    def _dict_payload(payload: dict[str, Any], key: str) -> dict[str, Any] | None:
        value = payload.get(key)
        return dict(value) if isinstance(value, dict) else None

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
