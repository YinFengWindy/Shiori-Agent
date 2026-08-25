import pytest

from desktop_bridge.voice.voice_assets import VoiceAssetLifecycle


def runtime_config(voice_id: str) -> dict:
    return {
        "tts": {
            "provider": "minimax",
            "voice_id": voice_id,
            "ownership": "shiori_managed",
        }
    }


def test_saved_role_claims_temporary_clone_and_retires_replaced_voice(tmp_path) -> None:
    deleted: list[str] = []
    lifecycle = VoiceAssetLifecycle(
        tmp_path,
        lambda *, voice_id, **_kwargs: deleted.append(voice_id),
    )
    lifecycle.track_clone(
        {
            "provider": "minimax",
            "voice_id": "Shiori_new",
            "ownership": "shiori_managed",
        }
    )

    lifecycle.reconcile_role_update(
        runtime_config("Shiori_old"), runtime_config("Shiori_new")
    )

    assert deleted == ["Shiori_old"]
    assert lifecycle.pending_assets == ()


def test_failed_cleanup_is_persisted_and_retried_after_restart(tmp_path) -> None:
    attempts: list[str] = []

    def fail_once(*, voice_id, **_kwargs) -> None:
        attempts.append(voice_id)
        raise RuntimeError("provider unavailable")

    lifecycle = VoiceAssetLifecycle(tmp_path, fail_once)
    lifecycle.track_clone(
        {
            "provider": "minimax",
            "voice_id": "Shiori_abandoned",
            "ownership": "shiori_managed",
        }
    )
    assert lifecycle.abandon_clone(
        provider="minimax",
        voice_id="Shiori_abandoned",
        ownership="shiori_managed",
    )
    assert attempts == ["Shiori_abandoned"]
    assert len(lifecycle.pending_assets) == 1

    retried: list[str] = []
    recovered = VoiceAssetLifecycle(
        tmp_path,
        lambda *, voice_id, **_kwargs: retried.append(voice_id),
    )
    recovered.recover_orphans([])

    assert retried == ["Shiori_abandoned"]
    assert recovered.pending_assets == ()


def test_unclaimed_clone_is_not_deleted_when_another_voice_is_retired(tmp_path) -> None:
    deleted: list[str] = []
    lifecycle = VoiceAssetLifecycle(
        tmp_path,
        lambda *, voice_id, **_kwargs: deleted.append(voice_id),
    )
    lifecycle.track_clone(
        {
            "provider": "minimax",
            "voice_id": "Shiori_unclaimed",
            "ownership": "shiori_managed",
        }
    )

    lifecycle.reconcile_role_update(
        runtime_config("Shiori_old"), runtime_config("Shiori_new")
    )

    assert deleted == ["Shiori_old"]
    assert lifecycle.pending_assets == ()


def test_corrupt_cleanup_state_fails_fast(tmp_path) -> None:
    (tmp_path / "voice_asset_cleanup.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(RuntimeError, match="清理状态无法读取"):
        VoiceAssetLifecycle(tmp_path, lambda **_kwargs: None)
