"""Actual TCP OAuth authorization server and MCP resource on separate origins."""

import asyncio
import base64
import hashlib
import json
from contextlib import suppress
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx2
from shiori_mcp_client.testing_http import HttpPeer


class OAuthPeer(HttpPeer):
    """Validate PKCE and rotate refresh tokens; never reuse the authenticated client."""

    def __init__(self):
        super().__init__()
        self.registrations = 0
        self.refreshes = 0
        self.exchanges = 0
        self.access = "access-canary-0"
        self.refresh_token = "refresh-canary-0"
        self.challenge = ""
        self.redirect_uri = ""
        self.token_bodies = []
        self.token_ports = []
        self.echo_secrets = False
        self.deny_refresh = False
        self.expiry = 3600
        self.hold_token = False
        self.token_waiting = asyncio.Event()
        self.token_release = asyncio.Event()

    async def __aenter__(self):
        await super().__aenter__()
        self.auth_server = await asyncio.start_server(self._accept, "127.0.0.1", 0)
        self.issuer = f"http://127.0.0.1:{self.auth_server.sockets[0].getsockname()[1]}"
        self.resource = self.url.split("?", 1)[0]
        return self

    async def __aexit__(self, *args):
        self.auth_server.close()
        await self.auth_server.wait_closed()
        await super().__aexit__(*args)

    async def authorize(self, url, *, state=None, issuer=None, break_pkce=False):
        async with httpx2.AsyncClient(follow_redirects=False) as browser:
            response = await browser.get(url)
            callback = response.headers["location"]
            parts = urlsplit(callback)
            query = parse_qs(parts.query)
            if state is not None:
                query["state"] = [state]
            if issuer is not None:
                query["iss"] = [issuer]
            if break_pkce:
                self.challenge = "wrong-challenge"
            callback = parts._replace(
                query=urlencode({key: value[0] for key, value in query.items()})
            ).geturl()
            await browser.get(callback)

    async def _handle(self, reader, writer):
        try:
            first = (await reader.readline()).decode().split()
            if not first:
                return
            method, target, _ = first
            headers = {}
            while line := await reader.readline():
                if line == b"\r\n":
                    break
                key, value = line.decode().split(":", 1)
                headers[key.lower()] = value.strip()
            body = await reader.readexactly(int(headers.get("content-length", 0)))
            self.requests.append((method, target, headers))
            path = urlsplit(target).path
            if path.startswith("/.well-known/oauth-protected-resource"):
                await self._json(
                    writer,
                    {"resource": self.resource, "authorization_servers": [self.issuer]},
                )
            elif path.startswith("/.well-known/"):
                await self._json(
                    writer,
                    {
                        "issuer": self.issuer,
                        "authorization_endpoint": self.issuer + "/authorize",
                        "token_endpoint": self.issuer + "/token",
                        "registration_endpoint": self.issuer + "/register",
                        "response_types_supported": ["code"],
                        "grant_types_supported": [
                            "authorization_code",
                            "refresh_token",
                        ],
                        "code_challenge_methods_supported": ["S256"],
                        "token_endpoint_auth_methods_supported": [
                            "none",
                            "client_secret_basic",
                            "client_secret_post",
                        ],
                        "authorization_response_iss_parameter_supported": True,
                    },
                )
            elif path == "/register":
                self.registrations += 1
                registration = json.loads(body)
                self.redirect_uri = registration["redirect_uris"][0]
                await self._json(writer, {**registration, "client_id": "dcr-client"})
            elif path == "/authorize":
                query = parse_qs(urlsplit(target).query)
                assert query["code_challenge_method"] == ["S256"]
                self.challenge = query["code_challenge"][0]
                uri = query["redirect_uri"][0]
                if self.redirect_uri:
                    assert uri == self.redirect_uri
                callback = (
                    uri
                    + "?"
                    + urlencode(
                        {
                            "code": "code-canary",
                            "state": query["state"][0],
                            "iss": self.issuer,
                        }
                    )
                )
                await self._raw(writer, 302, b"", {"location": callback})
            elif path == "/token":
                self.token_ports.append(writer.get_extra_info("sockname")[1])
                form = parse_qs(body.decode())
                self.token_bodies.append((form, headers))
                if form["grant_type"] == ["authorization_code"]:
                    self.exchanges += 1
                    challenge = (
                        base64.urlsafe_b64encode(
                            hashlib.sha256(form["code_verifier"][0].encode()).digest()
                        )
                        .decode()
                        .rstrip("=")
                    )
                    if challenge != self.challenge:
                        await self._json(
                            writer,
                            {
                                "error": "invalid_grant",
                                "error_description": "code-canary",
                            },
                            400,
                        )
                        return
                    if form["client_id"] == ["pre-client"]:
                        basic = (
                            "Basic "
                            + base64.b64encode(b"pre-client:secret-canary").decode()
                        )
                        assert headers.get("authorization") == basic or form.get(
                            "client_secret"
                        ) == ["secret-canary"]
                else:
                    if self.deny_refresh or form.get("refresh_token") != [
                        self.refresh_token
                    ]:
                        await self._json(writer, {"error": "invalid_grant"}, 400)
                        return
                    self.refreshes += 1
                    self.access = f"access-canary-{self.refreshes}"
                    self.refresh_token = f"refresh-canary-{self.refreshes}"
                if self.hold_token:
                    self.token_waiting.set()
                    await self.token_release.wait()
                await self._json(
                    writer,
                    {
                        "access_token": self.access,
                        "refresh_token": self.refresh_token,
                        "token_type": "Bearer",
                        "expires_in": self.expiry,
                    },
                )
            elif headers.get("authorization") != "Bearer " + self.access:
                await self._raw(
                    writer,
                    401,
                    b"access-canary-0",
                    {
                        "www-authenticate": f'Bearer resource_metadata="{self.resource.rsplit("/", 1)[0]}/.well-known/oauth-protected-resource"'
                    },
                )
            elif method != "POST":
                await self._reply(writer, 200 if method == "DELETE" else 405, b"")
            else:
                request = json.loads(body)
                if "id" not in request:
                    await self._reply(writer, 202, b"")
                else:
                    result = await self._rpc(request)
                    if self.echo_secrets and request["method"] == "tools/call":
                        result = {
                            "result": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": self.access
                                        + " "
                                        + self.refresh_token
                                        + " code-canary",
                                    }
                                ]
                            }
                        }
                    assert result is not None
                    await self._json(
                        writer, {"jsonrpc": "2.0", "id": request["id"], **result}
                    )
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()

    async def _json(self, writer, value, status=200):
        await self._raw(
            writer,
            status,
            json.dumps(value).encode(),
            {"content-type": "application/json"},
        )

    async def _raw(self, writer, status, body, headers):
        header = f"HTTP/1.1 {status} Response\r\nConnection: close\r\nContent-Length: {len(body)}\r\n"
        header += "".join(f"{key}: {value}\r\n" for key, value in headers.items())
        writer.write(header.encode() + b"\r\n" + body)
        await writer.drain()
