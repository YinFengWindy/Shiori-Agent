"""Private preference RPC save and change notifications use one persisted source."""

from shiori_sdk.testing.memory_context import FakeRpc
from plugins.desktop_pet.backend.voice_rpc import register_voice_preferences


async def test_save_broadcasts_only_after_private_settings_persist(tmp_path):
    rpc = FakeRpc()
    register_voice_preferences(rpc, tmp_path)
    assert (await rpc.handlers["voice.preferences.get"]({}))["enabled"] is False
    saved = await rpc.handlers["voice.preferences.set"](
        {"enabled": True, "asr": {"plugin_id": "new_plugin", "service_id": "asr"}}
    )
    assert rpc.events == [("voice.preferences.changed", saved)]
    restarted = FakeRpc()
    register_voice_preferences(restarted, tmp_path)
    assert await restarted.handlers["voice.preferences.get"]({}) == saved


async def test_context_reads_the_current_role_mood_and_rejects_missing_roles(tmp_path):
    import pytest
    from shiori_sdk.testing.roles import FakeRoles
    from shiori_sdk.testing.sessions import FakeSessions
    from plugins.desktop_pet.backend.voice_rpc import register_voice_context

    rpc, roles, sessions = FakeRpc(), FakeRoles(tmp_path), FakeSessions()
    roles.create_role(role_id="role", name="Role", system_prompt="Role")
    sessions.get_or_create("role:role").metadata["current_mood"] = "Excited"
    register_voice_context(rpc, roles, sessions)
    assert await rpc.handlers["voice.context.get"]({"role_id": "role"}) == {
        "role_id": "role",
        "session_key": "role:role",
        "mood": "Excited",
    }
    with pytest.raises(ValueError, match="不存在"):
        await rpc.handlers["voice.context.get"]({"role_id": "missing"})
    assert roles.extensions.values == {}
