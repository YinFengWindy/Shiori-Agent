"""Start preconditions: pet role, room, speech with a TTS service, valid login."""

import pytest
from shiori_sdk.testing.roles import FakeRoles

from plugins.desktop_pet.backend.bilibili_login import BilibiliLoginRequired
from plugins.desktop_pet.backend.live_config import LiveConfigStore
from plugins.desktop_pet.backend.live_gate import LiveStartGate
from plugins.desktop_pet.backend.voice_preferences import VoicePreferencesStore


async def test_each_precondition_is_reported_in_order(tmp_path):
    roles = FakeRoles(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="")
    configs, voice = LiveConfigStore(tmp_path), VoicePreferencesStore(tmp_path)
    state = {"pet": False, "login": False}

    async def credentials(role_id):
        if not state["login"]:
            raise BilibiliLoginRequired("B 站登录已失效，请重新扫码")

    gate = LiveStartGate(
        roles=roles,
        configs=configs,
        voice=voice,
        is_pet_role=lambda role_id: state["pet"],
        credentials=credentials,
    )
    with pytest.raises(ValueError, match="角色不存在"):
        await gate.check("ghost")
    with pytest.raises(ValueError, match="未启用桌宠"):
        await gate.check("mira")
    state["pet"] = True
    with pytest.raises(ValueError, match="尚未配置直播间"):
        await gate.check("mira")
    configs.update("mira", {"room_id": 6})
    with pytest.raises(ValueError, match="TTS"):
        await gate.check("mira")
    voice.write({"enabled": True})
    with pytest.raises(ValueError, match="TTS"):
        await gate.check("mira")
    voice.write({"enabled": True, "tts": {"plugin_id": "t", "service_id": "v"}})
    with pytest.raises(BilibiliLoginRequired):
        await gate.check("mira")
    state["login"] = True
    assert (await gate.check("mira")).room_id == 6
