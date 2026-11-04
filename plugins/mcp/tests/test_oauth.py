"""OAuth protocol, durable refresh, explicit browser consent and revocation races."""

import asyncio
import json
import logging
import socket

import pytest
from plugins.mcp.backend.registry import McpServerRegistry
from plugins.mcp.backend.models import LoginRequired
from .test_registry import _Processes, _Registration
from .oauth_peer import OAuthPeer


def registry(path):
    return McpServerRegistry(path, processes=_Processes(), registration=_Registration())


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def configured(path, peer, auth="none"):
    owner = registry(path)
    await owner.load_and_connect_all()
    options = {"redirect_port": port(), "auth_method": auth}
    if auth != "none":
        options.update(client_id="pre-client", client_secret="secret-canary")
    owner.save(
        {
            "server_id": "oauth",
            "config": {"transport": {"kind": "streamable_http", "auth": "oauth"}},
            "credentials": {
                "url": {"op": "replace", "value": peer.url},
                "oauth": {"op": "replace", "value": options},
            },
        }
    )
    await owner.wait_operations()
    return owner


async def authorization_url(owner):
    async with asyncio.timeout(5):
        while True:
            op = owner._states["oauth"].operation
            if op and op.get("authorization_url"):
                return str(op["authorization_url"])
            if op and op["status"] == "failed":
                pytest.fail(str(op))
            await asyncio.sleep(0.01)


async def login(owner, peer, **kwargs):
    owner.start_operation("oauth", "login")
    url = await authorization_url(owner)
    await peer.authorize(url, **kwargs)
    await owner.wait_operations()


@pytest.mark.parametrize("auth", ["none", "client_secret_basic", "client_secret_post"])
async def test_login_pkce_registration_restart_and_rotating_refresh(tmp_path, auth):
    async with OAuthPeer() as peer:
        path = tmp_path / "mcp_servers.json"
        owner = await configured(path, peer, auth)
        assert owner.oauth_binding("oauth").snapshot()["status"] == "login_required"
        assert peer.registrations == 0
        try:
            await login(owner, peer)
            assert owner._states["oauth"].status == "connected", owner.snapshot()
            assert await owner.call("oauth", "echo", {}) == "hello"
            binding = owner.oauth_binding("oauth")
            expiry = binding.store.record.expires_at
            assert expiry is not None
            await owner.shutdown()
            owner = registry(path)
            await owner.load_and_connect_all()
            await owner.wait_operations()
            binding = owner.oauth_binding("oauth")
            assert binding.store.record.expires_at == expiry
            assert peer.refreshes == 0
            binding.refresh()
            await asyncio.gather(
                owner.call("oauth", "echo", {}), owner.call("oauth", "echo", {})
            )
            assert peer.refreshes == 1
            assert binding.store.record.tokens.refresh_token == "refresh-canary-1"
            assert peer.registrations == (1 if auth == "none" else 0)
            binding.refresh()
            await owner.shutdown()
            owner = registry(path)
            await owner.load_and_connect_all()
            await owner.wait_operations()
            assert owner._states["oauth"].status == "connected", owner.snapshot()
            assert peer.refreshes == 2
            renewed = owner.oauth_binding("oauth").store.record.expires_at
            assert renewed is not None and renewed >= expiry
            assert set(peer.token_ports) == {int(peer.issuer.rsplit(":", 1)[1])}
            operation = owner._states["oauth"].operation
            assert operation is not None and not operation.get("authorization_url")
        finally:
            await owner.shutdown()


@pytest.mark.parametrize(
    "failure",
    [
        {"state": "state-canary"},
        {"issuer": "http://wrong.example"},
        {"break_pkce": True},
    ],
)
async def test_invalid_callback_or_pkce_cannot_authorize_or_leak(
    tmp_path, failure, caplog
):
    caplog.set_level(logging.DEBUG)
    async with OAuthPeer() as peer:
        owner = await configured(tmp_path / "mcp_servers.json", peer)
        try:
            # The simulated browser runs outside the adapter's log privacy context.
            logging.getLogger("httpx2").setLevel(logging.WARNING)
            logging.getLogger("httpcore2").setLevel(logging.WARNING)
            await login(owner, peer, **failure)
            assert owner._states["oauth"].status == "error"
            assert owner.oauth_binding("oauth").store.record.tokens is None
            public = json.dumps(owner.snapshot()) + owner.list_servers() + caplog.text
            for secret in (
                "code-canary",
                "state-canary",
                "access-canary",
                "refresh-canary",
                "code_verifier",
            ):
                assert secret not in public
        finally:
            await owner.shutdown()


async def test_cancel_logout_late_writes_and_failed_refresh_do_not_open_browser(
    tmp_path,
):
    async with OAuthPeer() as peer:
        owner = await configured(tmp_path / "mcp_servers.json", peer)
        try:
            owner.start_operation("oauth", "login")
            await authorization_url(owner)
            binding = owner.oauth_binding("oauth")
            old = binding.provider.storage
            callback_port = binding.options.redirect_port
            owner.cancel_operation("oauth")
            await owner.wait_operations()
            assert binding.listener is None
            with pytest.raises(OSError):
                await asyncio.open_connection("127.0.0.1", callback_port)
            with pytest.raises(LoginRequired):
                old.check()
            await login(owner, peer)
            peer.deny_refresh = True
            owner.start_operation("oauth", "refresh")
            await owner.wait_operations()
            assert owner.oauth_binding("oauth").snapshot()["status"] == "login_required"
            operation = owner._states["oauth"].operation
            assert operation is not None and "authorization_url" not in operation
            peer.deny_refresh = False
            await login(owner, peer)
            old = binding.provider.storage
            token = binding.store.record.tokens
            assert token is not None
            owner.start_operation("oauth", "logout")
            await owner.wait_operations()
            with pytest.raises(LoginRequired):
                await old.set_tokens(token)
            assert binding.store.record.tokens is None
            assert not owner._states["oauth"].wrappers
        finally:
            await owner.shutdown()


@pytest.mark.parametrize("action", ["cancel", "logout", "endpoint"])
async def test_late_token_response_cannot_restore_revoked_auth(tmp_path, action):
    async with OAuthPeer() as peer:
        owner = await configured(tmp_path / "mcp_servers.json", peer)
        try:
            peer.hold_token = True
            owner.start_operation("oauth", "login")
            url = await authorization_url(owner)
            await peer.authorize(url)
            await asyncio.wait_for(peer.token_waiting.wait(), 5)
            old_binding = owner.oauth_binding("oauth")
            if action == "cancel":
                owner.cancel_operation("oauth")
            elif action == "logout":
                owner.start_operation("oauth", "logout")
            else:
                config = owner.store.servers["oauth"]
                owner.save(
                    {
                        "server_id": "oauth",
                        "expected_revision": config.revision,
                        "config": {"transport": config.transport.model_dump()},
                        "credentials": {
                            "url": {
                                "op": "replace",
                                "value": peer.url + "&endpoint=new",
                            }
                        },
                    }
                )
            peer.token_release.set()
            await owner.wait_operations()
            assert old_binding.store.record.tokens is None
            assert old_binding.listener is None
            assert owner.oauth_binding("oauth").store.record.tokens is None
            assert not owner._states["oauth"].wrappers
        finally:
            await owner.shutdown()


async def test_private_tokens_reach_peer_but_not_model_or_read_rpc(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    async with OAuthPeer() as peer:
        owner = await configured(tmp_path / "mcp_servers.json", peer)
        try:
            logging.getLogger("httpx2").setLevel(logging.WARNING)
            logging.getLogger("httpcore2").setLevel(logging.WARNING)
            await login(owner, peer)
            peer.echo_secrets = True
            result = await owner.call("oauth", "echo", {})
            assert isinstance(result, str)
            assert "已隐藏" in result
            public = result + json.dumps(owner.snapshot()) + caplog.text
            for secret in (peer.access, peer.refresh_token, "code-canary"):
                assert secret not in public
            assert any(
                headers.get("authorization") == "Bearer " + peer.access
                for _, _, headers in peer.requests
            )
            assert peer.token_bodies[0][0]["code"] == ["code-canary"]
        finally:
            await owner.shutdown()


@pytest.mark.parametrize("outcome", ["result", "error"])
@pytest.mark.parametrize("fail_cleanup", [False, True])
async def test_refresh_during_call_and_disposed_binding_keep_reply_private(
    tmp_path, monkeypatch, outcome, fail_cleanup
):
    """A late result/error keeps both admission-time and rotated OAuth secrets hidden."""
    from shiori_sdk.mcp import McpToolError

    async with OAuthPeer() as peer:
        owner = await configured(tmp_path / "mcp_servers.json", peer)
        entered, release = asyncio.Event(), asyncio.Event()
        try:
            await login(owner, peer)
            binding = owner.oauth_binding("oauth")
            old_values = binding.secrets()
            binding.refresh()
            peer.echo_secrets = True
            session = owner._states["oauth"].session
            assert session is not None
            original = session.call

            async def delayed(tool, arguments, *, timeout=None):
                result = await original(tool, arguments, timeout=timeout)
                assert isinstance(result, str)
                entered.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    # Model an already-completed remote reply delivered after revoke.
                    pass
                text = json.dumps({"n": 1, "reply": result, "prior": old_values})
                if outcome == "error":
                    raise McpToolError(server="oauth", tool_name=tool, message=text)
                return text

            monkeypatch.setattr(session, "call", delayed)
            call = asyncio.create_task(owner.call("oauth", "echo", {}))
            await asyncio.wait_for(entered.wait(), 5)
            assert peer.refreshes == 1
            config = owner.store.servers["oauth"]
            if fail_cleanup:

                def failed_write(_record):
                    raise OSError("simulated OAuth cleanup failure")

                monkeypatch.setattr(binding.store, "write", failed_write)
            owner.save(
                {
                    "server_id": "oauth",
                    "expected_revision": config.revision,
                    "config": {"transport": config.transport.model_dump()},
                    "credentials": {
                        "url": {"op": "replace", "value": peer.url + "&endpoint=new"}
                    },
                }
            )
            release.set()
            if outcome == "error":
                with pytest.raises(McpToolError) as caught:
                    await call
                text = caught.value.message
            else:
                text = await call
                assert isinstance(text, str)
            assert json.loads(text)["n"] == 1
            assert "已隐藏" in text
            for secret in [*old_values, peer.access, peer.refresh_token, "code-canary"]:
                if secret:
                    assert secret not in text
            await owner.wait_operations()
            assert binding.store.record.tokens is None
            assert owner.oauth_binding("oauth") is not binding
            assert not owner._states["oauth"].wrappers
        finally:
            release.set()
            monkeypatch.undo()
            await owner.shutdown()


@pytest.mark.parametrize("action", ["save", "logout", "delete"])
async def test_credential_cleanup_io_failure_revokes_old_admission(
    tmp_path, monkeypatch, action
):
    """A committed endpoint/deletion or logout cannot leave old credentials callable."""
    from plugins.mcp.backend import oauth_store
    from plugins.mcp.backend.models import McpConfigError

    async with OAuthPeer() as peer:
        path = tmp_path / "mcp_servers.json"
        owner = await configured(path, peer)
        try:
            await login(owner, peer)
            binding = owner.oauth_binding("oauth")
            previous = owner.store.servers["oauth"]
            state = owner._states["oauth"]
            epoch = state.epoch
            wrapper = state.wrappers["echo"]
            old_storage = binding.provider.storage
            tokens = binding.store.record.tokens
            assert tokens is not None
            previous_calls = peer.calls["echo"]
            write = oauth_store.atomic_save_json

            def failed_write(destination, payload):
                if destination == binding.store.path:
                    raise OSError(
                        "simulated access-canary refresh-canary write failure"
                    )
                return write(destination, payload)

            with monkeypatch.context() as fault:
                fault.setattr(oauth_store, "atomic_save_json", failed_write)
                if action == "save":
                    owner.save(
                        {
                            "server_id": "oauth",
                            "expected_revision": previous.revision,
                            "config": {"transport": previous.transport.model_dump()},
                            "credentials": {
                                "url": {
                                    "op": "replace",
                                    "value": "http://127.0.0.1:1/replacement",
                                }
                            },
                        }
                    )
                    assert (
                        owner.store.credentials(owner.store.servers["oauth"]).url
                        == "http://127.0.0.1:1/replacement"
                    )
                    assert (
                        json.loads(path.read_text(encoding="utf-8"))["servers"][
                            "oauth"
                        ]["revision"]
                        == previous.revision + 1
                    )
                elif action == "logout":
                    owner.start_operation("oauth", "logout")
                else:
                    owner.delete("oauth", previous.revision)
                    assert (
                        "oauth"
                        not in json.loads(path.read_text(encoding="utf-8"))["servers"]
                    )
                assert state.epoch > epoch
                assert not state.wrappers
                with pytest.raises(McpConfigError):
                    await owner.call("oauth", "echo", {})
                with pytest.raises(McpConfigError):
                    await wrapper.execute()
                with pytest.raises(LoginRequired):
                    await old_storage.set_tokens(tokens)
                await owner.wait_operations()
                assert state.session is None
                operation = state.operation
                assert operation is not None and operation["status"] == "failed"
                assert "access-canary" not in json.dumps(operation)
                assert peer.calls["echo"] == previous_calls
        finally:
            await owner.shutdown()
