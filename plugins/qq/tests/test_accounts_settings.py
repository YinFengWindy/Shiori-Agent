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
