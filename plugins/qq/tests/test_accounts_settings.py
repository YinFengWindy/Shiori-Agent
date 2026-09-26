from __future__ import annotations

import pytest

from plugins.qq.backend.accounts_runtime import QQAccountsRuntime
from plugins.qq.backend.accounts_settings import validate_endpoint
from plugins.qq.backend.accounts_store import QQAccountsStore


def test_connection_drafts_require_a_forward_websocket_endpoint():
    assert validate_endpoint("ws://localhost:3001") == "ws://localhost:3001"
    assert validate_endpoint("wss://napcat.example/ws") == "wss://napcat.example/ws"
    for value in ("", "https://napcat.example", "ws://"):
        with pytest.raises(ValueError, match="WebSocket"):
            validate_endpoint(value)


@pytest.mark.asyncio
async def test_nonfinite_timeout_cannot_enter_private_config(tmp_path):
    store = QQAccountsStore(tmp_path)
    runtime = QQAccountsRuntime(store, object())
    with pytest.raises(ValueError, match="连接超时"):
        await runtime.save_draft(
            {
                "ws_uri": "ws://localhost:3001",
                "timeout_seconds": float("nan"),
            }
        )
    assert store.load() == {}


@pytest.mark.asyncio
async def test_saved_unverified_draft_can_be_reopened_and_removed(tmp_path):
    store = QQAccountsStore(tmp_path)
    runtime = QQAccountsRuntime(store, object())
    ref = (
        await runtime.save_draft(
            {"ws_uri": "ws://localhost:3001", "ws_token": "secret"}
        )
    )["ref"]
    restarted = QQAccountsRuntime(store, object())
    assert restarted.settings(ref=ref)["account"]["ws_uri"] == "ws://localhost:3001"
    assert restarted.settings(ref=ref)["account"]["has_token"] is True
    assert "secret" not in str(restarted.settings(ref=ref))
    await restarted.remove_draft(ref)
    assert store.load() == {}


@pytest.mark.asyncio
async def test_edited_legacy_draft_cannot_reappear_after_remove(tmp_path):
    store = QQAccountsStore(tmp_path)
    store.migrate_legacy(
        bot_uin="101",
        ws_uri="ws://localhost:3001",
        ws_token="old",
        timeout_seconds=5,
    )
    runtime = QQAccountsRuntime(store, object())
    await runtime.save_draft({"ref": "legacy", "ws_uri": "ws://localhost:3002"})
    assert store.load()["legacy"].auto_connect is False
    with pytest.raises(PermissionError, match="不能删除迁移记录"):
        await runtime.remove_draft("legacy")
    store.migrate_legacy(
        bot_uin="101",
        ws_uri="ws://localhost:3001",
        ws_token="old",
        timeout_seconds=5,
    )
    assert store.load()["legacy"].ws_uri == "ws://localhost:3002"
