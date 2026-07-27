from __future__ import annotations

from dataclasses import replace
from typing import Any

from core.common.channel_identifiers import chat_ids_equal

from .models import RoleChannelBindingConfig, RoleProactiveConfig, RoleRecord


class RoleBindingPolicy:
    """Validates role-owned channel contacts and proactive delivery targets."""

    def normalize_for_role(
        self,
        roles: list[RoleRecord],
        role_id: str,
        bindings: list[RoleChannelBindingConfig | dict[str, Any]],
    ) -> list[RoleChannelBindingConfig]:
        normalized = self.normalize(bindings)
        self.validate_desktop(role_id, normalized)
        self.ensure_unique(roles, role_id, normalized)
        return normalized

    def normalize(
        self,
        bindings: list[RoleChannelBindingConfig | dict[str, Any]],
    ) -> list[RoleChannelBindingConfig]:
        """Normalizes one role's binding list and contact cardinality."""
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
