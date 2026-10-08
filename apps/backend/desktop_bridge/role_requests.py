from __future__ import annotations

from collections.abc import Awaitable, Callable
import inspect
from typing import TYPE_CHECKING, Any

from core.roles import RoleAggregateService, RoleRecord
from core.roles.relationship_runtime.affection_prompts import stage_prompts_view

from .role_presenter import DesktopRolePresenter
from .role_card_export_service import DesktopRoleCardExportService

if TYPE_CHECKING:
    from core.roles import RoleRelationshipRuntimeService

# Same bounds as the memory timeline's page options.
_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100


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
        card_import_service: Any | None = None,
        card_export_service: DesktopRoleCardExportService | None = None,
        relationship_runtime: RoleRelationshipRuntimeService | None = None,
        publish_event: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self._role_service = role_service
        self._role_presenter = role_presenter
        self._card_import_service = card_import_service
        self._card_export_service = card_export_service
        self._relationship_runtime = relationship_runtime
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
        if method in {
            "roles.cardExport.preview",
            "roles.cardExport.read",
            "roles.cardExport.release",
        }:
            if self._card_export_service is None:
                raise RuntimeError("role card export service unavailable")
            handlers = {
                "roles.cardExport.preview": self._card_export_service.preview,
                "roles.cardExport.read": self._card_export_service.read,
                "roles.cardExport.release": self._card_export_service.release,
            }
            return await handlers[method](payload)
        if method == "roles.affection.history":
            return self._affection_history(payload)
        if method == "roles.affection.stagePrompts.get":
            return self._stage_prompts(payload)
        if method == "roles.affection.stagePrompts.set":
            return self._set_stage_prompts(payload)
        if method == "roles.update":
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
            await self._publish_event(
                {
                    "id": "",
                    "type": "event",
                    "method": "roles.updated",
                    "payload": {"role_id": role_id},
                }
            )
            return {"role": self._role_presenter.serialize(aggregate.role)}
        if method == "roles.delete":
            role_id = str(payload.get("role_id") or "").strip()
            self._role_service.repository.get_required(role_id)
            # The role's accounts go first, through their loaded plugins; a
            # failed cleanup keeps the role so the deletion can be retried.
            deleted_accounts = (
                await self._role_service.repository.store.accounts.delete_role_accounts(
                    role_id
                )
            )
            deleted, session_deleted = self._role_service.delete_role(role_id)
            return {
                "deleted": deleted,
                "session_deleted": session_deleted,
                "deleted_accounts": deleted_accounts,
            }
        # `roles.pets.import` / `.remove` / `.select` used to live here. They are
        # now `plugin.desktop_pet.pets.*`, registered by the plugin that owns
        # them (#181-D), so the core bridge no longer knows what a pet package
        # is — and the desktop's package manager, which is now plugin UI, can
        # only reach its own namespace anyway.
        return None

    def _affection_history(self, payload: dict[str, Any]) -> dict[str, Any]:
        """One newest-first history page plus the current summary.

        Pages are 1-based like the memory timeline; an uninitialized role
        answers ``affection: None`` with no items.
        """
        if self._relationship_runtime is None:
            raise RuntimeError("relationship runtime unavailable")
        affection = self._relationship_runtime.affection
        role_id = str(payload.get("role_id") or "").strip()
        self._role_service.repository.get_required(role_id)
        page = max(1, int(payload.get("page") or 1))
        page_size = int(payload.get("page_size") or _DEFAULT_PAGE_SIZE)
        page_size = max(1, min(_MAX_PAGE_SIZE, page_size))
        entries, total = affection.history_page(role_id, page=page, page_size=page_size)
        return {
            "role_id": role_id,
            "affection": affection.summary(role_id),
            "items": [{"id": id_, **entry.to_dict()} for id_, entry in entries],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _stage_prompts(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Each stage's injected guidance, its default and whether it is overridden."""
        role = self._role_service.repository.get_required(
            str(payload.get("role_id") or "").strip()
        )
        return self._stage_prompts_payload(role)

    def _set_stage_prompts(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Writes the given stages' guidance; ``null``, blank or default text restores the default.

        ``prompts`` maps stage names to text and may name only some stages;
        the others keep their current guidance. Answers like the read.
        """
        changes = payload.get("prompts")
        if not isinstance(changes, dict):
            raise ValueError("prompts 必须是以阶段名为键的对象")
        role = self._role_service.update_affection_stage_prompts(
            str(payload.get("role_id") or "").strip(), changes
        )
        return self._stage_prompts_payload(role)

    @staticmethod
    def _stage_prompts_payload(role: RoleRecord) -> dict[str, Any]:
        return {
            "role_id": role.id,
            "stages": stage_prompts_view(role.affection_stage_prompts),
        }

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
