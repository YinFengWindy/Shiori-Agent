"""Persistent profile ownership is enforced by the operating system."""

import pytest

from plugins.browser_use.backend.profile import ProfileLease


def test_profile_lock_prevents_parallel_owners_and_preserves_data(tmp_path):
    first = ProfileLease(tmp_path)
    cookie = tmp_path / "site-state"
    cookie.write_text("logged-in", encoding="utf-8")
    try:
        with pytest.raises(RuntimeError, match="占用"):
            ProfileLease(tmp_path)
    finally:
        first.close()
    second = ProfileLease(tmp_path)
    second.close()
    assert cookie.read_text(encoding="utf-8") == "logged-in"
