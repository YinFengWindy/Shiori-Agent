"""Reference adoption and garbage collection must respect active server readers."""

import pytest
from shiori_sdk.files.json import atomic_save_json


@pytest.mark.parametrize("seconds", [2.9, 10.1])
def test_reference_duration_limits(import_reference, seconds):
    with pytest.raises(ValueError, match="3–10"):
        import_reference(seconds)


def test_reference_silence_rejected(import_reference):
    with pytest.raises(ValueError, match="静音"):
        import_reference(signal=0)


def test_replaced_reference_retained_until_pin_ends(configured, import_reference):
    references = configured
    old = references.store.read().roles["role"].default.asset
    new = import_reference(signal=2)
    with references.pin(old) as path:
        references.store.save_role("role", {"default": {"asset": new}})
        references.collect()
        assert path.exists()
    assert not path.exists()
    assert references.path(new).exists()


def test_restart_reconciles_deleted_roles_but_preserves_uncertain_assets(configured):
    references = configured
    asset = references.store.read().roles["role"].default.asset
    path = references.path(asset)
    marker = references.store.root / "inference.json"
    atomic_save_json(marker, {"state": "unknown"})
    references.reconcile(set())
    assert references.store.read().roles == {}
    assert path.exists()
    marker.unlink()
    references.collect()
    assert not path.exists()
