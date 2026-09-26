"""Account metadata is validated and repaired when loaded from disk."""

from __future__ import annotations

import pytest

from core.accounts.models import AccountRecord
from core.accounts.persistence import load_accounts, save_accounts


def test_load_clears_stale_role_ownership_durably(tmp_path):
    path = tmp_path / "accounts.json"
    row = AccountRecord("id", "plugin", "platform", "101", "config", role_id="gone")
    save_accounts(path, {row.id: row})

    loaded = load_accounts(path, lambda _role_id: False)
    assert loaded["id"].role_id is None
    assert loaded["id"].ownership_version == 1
    assert load_accounts(path, lambda _role_id: False)["id"].ownership_version == 1


def test_load_rejects_duplicate_physical_identity(tmp_path):
    path = tmp_path / "accounts.json"
    rows = {
        "first": AccountRecord("first", "plugin", "platform", "101", "one"),
        "second": AccountRecord("second", "plugin", "platform", "101", "two"),
    }
    save_accounts(path, rows)

    with pytest.raises(ValueError, match="Duplicate account identity"):
        load_accounts(path, lambda _role_id: True)
