from __future__ import annotations

from core.roles import RoleStore


def test_role_store_persists_proactive_policy_and_keeps_it_when_target_is_removed(tmp_path):
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")
    store.update_role(
        "mira",
        channel_bindings=[
            {"channel": "telegram", "chat_id": "42", "allow_from": []},
        ],
        proactive={
            "enabled": True,
            "target_channel": "telegram",
            "target_chat_id": "42",
            "profile": "quiet",
            "overrides": {"gate": {"judge_send_threshold": 0.8}},
            "agent": {"model": "agent-model", "max_steps": 12},
            "drift": {"enabled": True, "min_interval_hours": 6},
        },
    )

    updated = store.update_role("mira", channel_bindings=[])
    reloaded = store.get_role("mira")

    assert updated.proactive.enabled is False
    assert updated.proactive.target_channel == ""
    assert reloaded is not None
    assert reloaded.proactive.profile == "quiet"
    assert reloaded.proactive.agent["model"] == "agent-model"
    assert reloaded.proactive.drift["min_interval_hours"] == 6
    assert reloaded.proactive.policy_configured is True

