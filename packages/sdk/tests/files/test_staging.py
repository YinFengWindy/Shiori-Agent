"""Native import ownership remains enforced across path and size variants."""

import pytest
from shiori_sdk.files.staging import staged_import_file


def test_only_the_named_namespace_is_readable(tmp_path):
    directory = tmp_path / "private_runtime/imports/owner-audio"
    directory.mkdir(parents=True)
    source = directory / "source.wav"
    source.write_bytes(b"1234")
    assert (
        staged_import_file(
            tmp_path, "owner-audio", str(source), suffix=".wav", max_bytes=4
        )
        == source.resolve()
    )
    for namespace, suffix, limit in [
        ("other", ".wav", 4),
        ("owner-audio", ".zip", 4),
        ("owner-audio", ".wav", 3),
    ]:
        with pytest.raises(ValueError):
            staged_import_file(
                tmp_path, namespace, str(source), suffix=suffix, max_bytes=limit
            )
    with pytest.raises(ValueError):
        staged_import_file(
            tmp_path, "../escape", str(source), suffix=".wav", max_bytes=4
        )
