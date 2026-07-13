from __future__ import annotations

from pathlib import Path

from bootstrap.tools import _role_owns_channel_target, _validate_role_target
from core.roles import RoleRepository, RoleStore


def test_role_target_validation_uses_canonical_chat_id_comparison(
    tmp_path: Path,
) -> None:
    store = RoleStore(tmp_path)
    role = store.create_role(
        role_id="mira",
        name="Mira",
        description="",
        system_prompt="You are Mira.",
    )
    store.update_role(
        role.id,
        channel_bindings=[
            {"channel": "qq", "chat_id": "gqq:42", "allow_from": []}
        ],
    )

    assert _role_owns_channel_target(
        RoleRepository(store),
        role_id=role.id,
        channel="qq",
        chat_id="42",
    )


def test_role_target_validation_explains_wrong_channel_for_bound_chat(
    tmp_path: Path,
) -> None:
    store = RoleStore(tmp_path)
    role = store.create_role(
        role_id="mira",
        name="Mira",
        description="",
        system_prompt="You are Mira.",
    )
    store.update_role(
        role.id,
        channel_bindings=[
            {"channel": "qqbot", "chat_id": "c2c:user-1", "allow_from": []}
        ],
    )

    result = _validate_role_target(
        RoleRepository(store),
        role_id=role.id,
        channel="qq",
        chat_id="c2c:user-1",
    )

    assert isinstance(result, str)
    assert "已绑定渠道 qqbot" in result
    assert "请使用 channel=qqbot" in result
