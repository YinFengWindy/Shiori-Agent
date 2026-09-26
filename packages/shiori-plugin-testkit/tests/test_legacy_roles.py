"""Legacy manifest fixture support stays outside production role writers."""

from __future__ import annotations

from core.roles.store import RoleStore
from shiori_plugin_testkit.legacy_roles import seed_legacy_bindings


def test_seed_legacy_bindings_preserves_other_role_fields(tmp_path):
    store = RoleStore(tmp_path)
    store.create_role(role_id="mira", name="Mira", system_prompt="Mira")
    seeded = seed_legacy_bindings(
        tmp_path,
        "mira",
        [{"channel": "qq", "chat_id": "gqq:42", "chat_type": "group"}],
    )

    assert seeded.channel_bindings[0].chat_id == "gqq:42"
    reloaded = RoleStore(tmp_path).get_role("mira")
    assert reloaded is not None
    assert reloaded.name == "Mira"
    assert reloaded.channel_bindings == seeded.channel_bindings
