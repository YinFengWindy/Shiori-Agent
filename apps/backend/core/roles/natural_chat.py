"""The single read of a role's natural-chat switch."""

from __future__ import annotations

from core.roles.models import RoleRecord


def natural_chat_enabled(role: RoleRecord | None) -> bool:
    """Whether ``role`` explicitly turns natural chat on.

    The role record's ``runtime_config`` is the only source. Opening a role
    session copies that mapping into ``metadata["role_runtime_config"]`` for
    other fields; that copy is not a switch. Only boolean ``True`` counts.
    A missing role, a missing key, and every other value are off.
    """

    if role is None:
        return False
    return role.runtime_config.get("natural_chat_enabled") is True
