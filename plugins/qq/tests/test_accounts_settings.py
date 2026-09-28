from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from plugins.qq.backend.accounts_runtime import QQAccountsRuntime
from plugins.qq.backend.accounts_settings import validate_endpoint
from plugins.qq.backend.accounts_store import QQAccountsStore, QQConnectionConfig


def test_connection_drafts_require_a_forward_websocket_endpoint():
    assert validate_endpoint("ws://localhost:3001") == "ws://localhost:3001"
    assert validate_endpoint("wss://napcat.example/ws") == "wss://napcat.example/ws"
    for value in ("", "https://napcat.example", "ws://"):
        with pytest.raises(ValueError, match="WebSocket"):
            validate_endpoint(value)


@pytest.mark.asyncio
async def test_nonfinite_timeout_cannot_enter_private_config(tmp_path):
    store = QQAccountsStore(tmp_path)
    runtime = QQAccountsRuntime(store, _Accounts())
    with pytest.raises(ValueError, match="连接超时"):
        await runtime.save_draft(
            {
                "role_id": "mira",
                "ws_uri": "ws://localhost:3001",
                "timeout_seconds": float("nan"),
            }
        )
    assert store.load() == {}


@pytest.mark.asyncio
async def test_saved_unverified_draft_can_be_reopened_and_removed(tmp_path):
    store = QQAccountsStore(tmp_path)
    runtime = QQAccountsRuntime(store, _Accounts())
    ref = (
        await runtime.save_draft(
            {"role_id": "mira", "ws_uri": "ws://localhost:3001", "ws_token": "secret"}
        )
    )["ref"]
    restarted = QQAccountsRuntime(store, _Accounts())
    assert restarted.settings(ref=ref)["account"]["ws_uri"] == "ws://localhost:3001"
    assert restarted.settings(ref=ref)["account"]["has_token"] is True
    assert "secret" not in str(restarted.settings(ref=ref))
    await restarted.remove_draft(ref)
    assert store.load() == {}


@pytest.mark.asyncio
async def test_ownerless_draft_cannot_be_claimed(tmp_path):
    store = QQAccountsStore(tmp_path)
    store.save({"aa": QQConnectionConfig("aa", "ws://localhost:3001", "old")})
    runtime = QQAccountsRuntime(store, _Accounts())
    # An ownerless draft is never taken over by the role editing it.
    with pytest.raises(ValueError, match="未归属"):
        await runtime.save_draft(
            {"role_id": "mira", "ref": "aa", "ws_uri": "ws://localhost:3002"}
        )
    assert store.load()["aa"].ws_uri == "ws://localhost:3001"
    assert store.load()["aa"].role_id is None


@pytest.mark.asyncio
async def test_managed_draft_uses_private_endpoint_without_external_fields(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "plugins.qq.backend.accounts_settings.managed_available", lambda: True
    )
    store = QQAccountsStore(tmp_path)
    runtime = QQAccountsRuntime(store, _Accounts())
    ref = (await runtime.save_draft({"role_id": "mira", "mode": "managed"}))["ref"]
    saved = store.load()[ref]
    assert saved.mode == "managed"
    assert saved.ws_uri.startswith("ws://127.0.0.1:")
    assert saved.ws_token
    assert runtime.settings(ref=ref)["account"]["mode"] == "managed"
    assert saved.ws_token not in str(runtime.settings(ref=ref))


class _Accounts:
    def __init__(self) -> None:
        self.reports: list[tuple[str, str]] = []

    def register(
        self,
        *,
        platform,
        platform_account_id,
        config_ref,
        role_id,
        display_name,
        response_rules=None,
    ):
        return SimpleNamespace(record=SimpleNamespace(id=f"qq-{platform_account_id}"))

    def check_owner(self, *, config_ref, role_id, **_identity):
        if not role_id:
            raise ValueError("账号没有所属角色")

    def role_exists(self, role_id):
        return True

    def register_saved(self, **fields):
        # The host refuses an entry without an owner; the plugin must skip it.
        return self.register(**fields) if fields.get("role_id") else None

    def report(self, account_id, *, connection, capabilities=frozenset(), error=""):
        self.reports.append((account_id, connection))


class _Socket:
    closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_deleted_account_is_disconnected_and_its_napcat_data_purged(tmp_path):
    store = QQAccountsStore(tmp_path)
    store.save(
        {
            ref: QQConnectionConfig(
                ref,
                "ws://127.0.0.1:3001",
                f"token-{ref}",
                expected_uin=uin,
                auto_connect=False,
                verified=True,
                mode="managed",
                role_id="mira",
            )
            for ref, uin in (("aa", "101"), ("bb", "202"))
        }
    )
    accounts = _Accounts()
    runtime = QQAccountsRuntime(store, accounts)
    socket = _Socket()
    runtime._sockets["aa"] = socket
    reconnect = asyncio.create_task(asyncio.sleep(3600))
    runtime._tasks["aa"] = reconnect
    files = runtime._managed._files
    for ref in ("aa", "bb"):
        login = files.account_dir(ref) / "profile/AppData/Roaming/Tencent/QQNT"
        login.mkdir(parents=True)
        (login / "session.db").write_text("login", encoding="utf-8")

    await runtime.disconnect_account("aa")

    assert socket.closed and reconnect.cancelled()
    # Disconnecting alone keeps every credential and login file for a retry.
    assert "token-aa" in store.path.read_text(encoding="utf-8")
    assert (files.account_dir("aa") / "profile").is_dir()

    await runtime.purge_account("aa")

    assert not files.account_dir("aa").exists()
    assert (files.account_dir("bb") / "profile").is_dir()
    assert list(store.load()) == ["bb"]
    assert "token-aa" not in store.path.read_text(encoding="utf-8")
    assert [row["ref"] for row in runtime.settings()["accounts"]] == ["bb"]
    with pytest.raises(KeyError):
        runtime._ref_for("qq-101")
    assert accounts.reports == []
    await runtime.disconnect_account("aa")
    await runtime.purge_account("aa")
    assert list(QQAccountsStore(tmp_path).load()) == ["bb"]
