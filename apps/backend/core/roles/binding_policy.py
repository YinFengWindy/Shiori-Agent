from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from core.common.channel_chat_types import (
    CHAT_TYPE_PRIVATE,
    ChatTypeDeclarations,
    validate_chat_id_for_type,
)
from core.common.channel_directory import DESKTOP_CHANNEL
from core.common.channel_identifiers import chat_ids_equal

from .models import (
    RoleChannelBindingConfig,
    RoleProactiveCandidate,
    RoleProactiveConfig,
    RoleRecord,
    keeps_proactive_enabled,
)


class RoleBindingPolicy:
    """Validates role-owned channel sessions and proactive candidate sessions.

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
        """Normalizes one role's binding list and checks its session types.

        Blacklists are checked by ``RoleChannelBindingConfig`` itself (group
        bindings only).

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
        self._validate_chat_types(normalized, previous or [])
        return normalized

    def validate_desktop(
        self, role_id: str, bindings: list[RoleChannelBindingConfig]
    ) -> None:
        """Validates the role-derived desktop chat and its private session type."""
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
        """Validates the candidate sessions and stores them in binding order.

        Every candidate must name one of ``bindings``; enabling proactive
        delivery requires at least one candidate.
        """
        normalized = (
            proactive
            if isinstance(proactive, RoleProactiveConfig)
            else RoleProactiveConfig.from_dict(proactive)
        )
        bound = {RoleProactiveCandidate.of_binding(binding) for binding in bindings}
        unbound = next(
            (item for item in normalized.candidates if item not in bound), None
        )
        if unbound is not None:
            raise ValueError(
                "主动推送候选会话必须是当前角色已绑定的会话: "
                f"{unbound.channel}:{unbound.chat_id}"
            )
        normalized = replace(
            normalized,
            candidates=_candidates_in_binding_order(normalized.candidates, bindings),
        )
        if normalized.enabled and not normalized.candidates:
            raise ValueError("启用主动推送时至少要选择一个接收会话")
        return normalized

    @staticmethod
    def prune_proactive_candidates(
        proactive: RoleProactiveConfig,
        bindings: list[RoleChannelBindingConfig],
    ) -> RoleProactiveConfig:
        """Drops candidates whose binding was removed, keeping binding order.

        Proactive delivery that is left without any candidate is disabled, since
        it has nowhere to send.
        """
        candidates = _candidates_in_binding_order(proactive.candidates, bindings)
        return replace(
            proactive,
            candidates=candidates,
            enabled=keeps_proactive_enabled(proactive.enabled, candidates),
        )

    def _validate_chat_types(
        self,
        bindings: list[RoleChannelBindingConfig],
        previous: list[RoleChannelBindingConfig],
    ) -> None:
        """Checks session types against the bound manifest declarations.

        Skipping before ``bind_chat_types`` only serves isolated core use (unit
        tests, scripts); in production ``CoreRuntime.start`` binds the
        declarations before any bridge request can save a role.
        """
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
            binding.channel == DESKTOP_CHANNEL
            and binding.chat_type != CHAT_TYPE_PRIVATE
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


def _candidates_in_binding_order(
    candidates: Iterable[RoleProactiveCandidate],
    bindings: list[RoleChannelBindingConfig],
) -> tuple[RoleProactiveCandidate, ...]:
    """Keeps the candidates that are still bound, ordered like ``bindings``."""
    selected = set(candidates)
    return tuple(
        candidate
        for candidate in map(RoleProactiveCandidate.of_binding, bindings)
        if candidate in selected
    )
