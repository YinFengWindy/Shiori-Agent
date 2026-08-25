from desktop_bridge.voice.role_tts_settings import resolve_role_tts_settings


def test_resolve_role_tts_settings_uses_one_mood_snapshot_and_valid_mapping() -> None:
    settings = resolve_role_tts_settings(
        {
            "tts": {
                "voice_id": "mira-voice",
                "speed": 1.4,
                "mood_tts_emotions": {"开心": "happy", "未知": "not-supported"},
            }
        },
        "开心",
    )

    assert settings.voice_id == "mira-voice"
    assert settings.provider == "minimax"
    assert settings.speed == 1.4
    assert settings.emotion == "happy"
    assert settings.mood == "开心"
    assert resolve_role_tts_settings(
        {"tts": {"voice_id": "voice", "speed": 9}},
        "未知",
    ).speed == 1.0
