from __future__ import annotations

from dataclasses import replace
from typing import Any

from core.common.channel_chat_types import (
    CHAT_TYPE_PRIVATE,
    ChatTypeDeclarations,
    validate_chat_id_for_type,
)
from core.common.channel_directory import DESKTOP_CHANNEL
from core.common.channel_identifiers import chat_ids_equal

from .models import RoleChannelBindingConfig, RoleProactiveConfig, RoleRecord


class RoleBindingPolicy:
    """Validates role-owned channel contacts and proactive delivery targets.

    Session types are checked against the channels' manifest declarations,
    which the host binds once plugins are discovered; every plugin channel
    must declare them. A channel no installed plugin declares (its plugin was
    uninstalled) only keeps bindings already saved unchanged, so the role stays
    editable while such a binding is shown read-only. Before the host binds
    declarations (isolated core use) session types are not checked.
    """

    def __init__(self) -> None:
        self._chat_types: ChatTypeDeclarations | None = None

    def bind_chat_types(self, declarations: ChatTypeDeclarations) -> None:
        """Checks bindings against these declared channel session types from now on."""
        self._chat_types = declarations

    def normalize_for_role(
        self,
        roles: list[RoleRecord],
        role_id: str,
        bindings: list[RoleChannelBindingConfig | dict[str, Any]],
    ) -> list[RoleChannelBindingConfig]:
        previous = next(
            (role.channel_bindings for role in roles if role.id == role_id), []
        )
        normalized = self.normalize(bindings, previous=previous)
        self.validate_desktop(role_id, normalized)
        self.ensure_unique(roles, role_id, normalized)
        return normalized

    def normalize(
        self,
        bindings: list[RoleChannelBindingConfig | dict[str, Any]],
        *,
        previous: list[RoleChannelBindingConfig] | None = None,
    ) -> list[RoleChannelBindingConfig]:
        """Normalizes one role's binding list, contact cardinality and session types.

        ``previous`` is the role's saved list; it decides which bindings on a
        channel without a declaration may be kept.
        """
        normalized = [
            (
                item
                if isinstance(item, RoleChannelBindingConfig)
                else RoleChannelBindingConfig.from_dict(item)
            )
            for item in bindings
        ]
        for index, item in enumerate(normalized):
            if any(
                other.channel == item.channel
                and chat_ids_equal(item.channel, other.chat_id, item.chat_id)
                for other in normalized[:index]
            ):
                raise ValueError("同一角色不能重复绑定相同渠道会话")
        self._validate_external_contacts(normalized)
        self._validate_chat_types(normalized, previous or [])
        return normalized

    def validate_desktop(
        self, role_id: str, bindings: list[RoleChannelBindingConfig]
    ) -> None:
        """Validates the role-derived desktop chat and contact rules."""
        self._validate_desktop(role_id, bindings)

    def ensure_unique(
        self,
        roles: list[RoleRecord],
        role_id: str,
        bindings: list[RoleChannelBindingConfig],
    ) -> None:
        """Rejects channel sessions already assigned to another role."""
        self._ensure_unique_across_roles(roles, role_id, bindings)

    @staticmethod
    def normalize_proactive(
        proactive: RoleProactiveConfig | dict[str, Any],
        bindings: list[RoleChannelBindingConfig],
    ) -> RoleProactiveConfig:
        normalized = (
            proactive
            if isinstance(proactive, RoleProactiveConfig)
            else RoleProactiveConfig.from_dict(proactive)
        )
        if normalized.enabled and (
            not normalized.target_channel or not normalized.target_chat_id
        ):
            raise ValueError("启用主动推送时必须显式选择一个目标渠道")
        if (
            normalized.target_channel
            and normalized.target_chat_id
            and not RoleBindingPolicy._contains_target(bindings, normalized)
        ):
            raise ValueError("主动推送目标必须是当前角色已绑定的渠道")
        return normalized

    @staticmethod
    def disable_missing_proactive_target(
        proactive: RoleProactiveConfig,
        bindings: list[RoleChannelBindingConfig],
    ) -> RoleProactiveConfig:
        if proactive.enabled and not RoleBindingPolicy._contains_target(
            bindings, proactive
        ):
            return replace(
                proactive,
                enabled=False,
                target_channel="",
                target_chat_id="",
            )
        return proactive

    @staticmethod
    def _contains_target(
        bindings: list[RoleChannelBindingConfig], proactive: RoleProactiveConfig
    ) -> bool:
        return any(
            binding.channel == proactive.target_channel
            and chat_ids_equal(
                binding.channel,
                binding.chat_id,
                proactive.target_chat_id,
            )
            for binding in bindings
        )

    @staticmethod
    def _validate_external_contacts(
        bindings: list[RoleChannelBindingConfig],
    ) -> None:
        for binding in bindings:
            if binding.channel != "desktop" and len(binding.allow_from) != 1:
                raise ValueError("外部渠道必须绑定且仅绑定一个联系人")

    def _validate_chat_types(
        self,
        bindings: list[RoleChannelBindingConfig],
        previous: list[RoleChannelBindingConfig],
    ) -> None:
        if self._chat_types is None:
            return
        for binding in bindings:
            if binding.channel == DESKTOP_CHANNEL:
                continue
            declarations = self._chat_types.get(binding.channel)
            if declarations is not None:
                validate_chat_id_for_type(
                    binding.chat_id, binding.chat_type, declarations
                )
            elif binding not in previous:
                raise ValueError(
                    f"渠道 {binding.channel} 没有已安装的插件提供，不能新增或修改其绑定"
                )

    @staticmethod
    def _validate_desktop(
        role_id: str,
        bindings: list[RoleChannelBindingConfig],
    ) -> None:
        expected_chat_id = f"role:{role_id}"
        if any(
            binding.channel == "desktop" and binding.chat_id != expected_chat_id
            for binding in bindings
        ):
            raise ValueError(f"桌面端渠道必须绑定当前角色会话: {expected_chat_id}")
        if any(
            binding.channel == "desktop" and binding.allow_from for binding in bindings
        ):
            raise ValueError("桌面端渠道不支持允许对象")
        if any(
            binding.channel == "desktop" and binding.chat_type != CHAT_TYPE_PRIVATE
            for binding in bindings
        ):
            raise ValueError("桌面端渠道的会话类型只能是私聊")

    @staticmethod
    def _ensure_unique_across_roles(
        roles: list[RoleRecord],
        role_id: str,
        bindings: list[RoleChannelBindingConfig],
    ) -> None:
        assigned = {
            (binding.channel, binding.chat_id)
            for other in roles
            if other.id != role_id
            for binding in other.channel_bindings
        }
        conflict = next(
            (
                (binding.channel, binding.chat_id)
                for binding in bindings
                if any(
                    item_channel == binding.channel
                    and chat_ids_equal(binding.channel, item_chat_id, binding.chat_id)
                    for item_channel, item_chat_id in assigned
                )
            ),
            None,
        )
        if conflict is not None:
            raise ValueError(f"渠道会话已绑定其他角色: {conflict[0]}:{conflict[1]}")
