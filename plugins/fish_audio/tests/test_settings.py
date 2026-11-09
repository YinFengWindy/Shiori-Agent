"""Credential secrecy and independent per-role persistence."""

import pytest

from plugins.fish_audio.backend.settings import RoleVoice, VoiceStore


def test_global_edits_preserve_roles_and_key_is_only_explicitly_cleared(tmp_path):
    store = VoiceStore(tmp_path)
    store.save_role("alice", RoleVoice(reference_id="alice", speed=1.2))
    store.save_role("bob", RoleVoice(reference_id="bob", speed=0.8))
    assert store.save_settings({"api_key": "private-key", "tts_model": "s2-pro"}) == {
        "has_api_key": True,
        "tts_model": "s2-pro",
    }
    store.save_settings({"api_key": "", "tts_model": "s2.1-pro-free"})
    reloaded = VoiceStore(tmp_path)
    assert reloaded.read().settings.api_key == "private-key"
    assert reloaded.read().roles == {
        "alice": RoleVoice(reference_id="alice", speed=1.2),
        "bob": RoleVoice(reference_id="bob", speed=0.8),
    }
    reloaded.save_settings({"clear_api_key": True, "tts_model": "s2.1-pro"})
    assert reloaded.read().settings.api_key == ""
    assert reloaded.read().roles == store.read().roles


def test_invalid_secret_update_does_not_leak_input_or_overwrite_document(tmp_path):
    store = VoiceStore(tmp_path)
    store.save_settings({"api_key": "previous", "tts_model": "s2-pro"})
    previous = store.read()
    secret = "private-secret-" * 400
    with pytest.raises(ValueError) as error:
        store.save_settings({"api_key": secret, "tts_model": "s2-pro"})
    assert "private-secret" not in str(error.value)
    assert store.read() == previous
    with pytest.raises(ValueError):
        store.save_settings(
            {"api_key": "new", "clear_api_key": True, "tts_model": "s2-pro"}
        )
    assert store.read() == previous


def test_reconcile_removes_only_deleted_roles(tmp_path):
    store = VoiceStore(tmp_path)
    store.save_role("alice", RoleVoice(reference_id="alice"))
    store.save_role("bob", RoleVoice(reference_id="bob"))
    store.reconcile({"bob"})
    assert store.read().roles == {"bob": RoleVoice(reference_id="bob")}
