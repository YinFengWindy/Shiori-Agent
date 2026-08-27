from __future__ import annotations

from pathlib import Path

from core.roles import RoleAggregateService, RoleStore
from session.manager import SessionManager


def test_qq_group_binding_accepts_bare_role_chat_id(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    roles = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=manager,
    )
    role = roles.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="You are Mira.",
    ).role
    _ = roles.repository.update_role(
        role.id,
        channel_bindings=[
            {"channel": "qq", "chat_id": "831907794", "allow_from": ["owner"]}
        ],
    )

    binding = roles.bindings.get_binding("qq", "gqq:831907794")

    assert binding is not None
    assert binding.role_id == role.id
