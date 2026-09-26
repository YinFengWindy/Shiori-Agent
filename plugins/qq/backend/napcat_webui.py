"""Authenticated loopback calls to a managed NapCat login WebUI."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import urllib.request
from typing import Any, Callable


class NapCatWebUi:
    """Serializes per-account WebUI calls and caches short-lived credentials."""

    def __init__(self, metadata: Callable[[str], dict[str, Any]]) -> None:
        self._metadata = metadata
        self._credentials: dict[str, tuple[str, float]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def reset(self, ref: str) -> None:
        """Forgets credentials when the owned process starts or stops."""
        self._credentials.pop(ref, None)

    def _request(self, ref: str, route: str, body: dict[str, Any]) -> Any:
        metadata = self._metadata(ref)
        base = f"http://127.0.0.1:{metadata['webui_port']}/api"
        cached = self._credentials.get(ref)
        if cached is None or time.monotonic() >= cached[1]:
            secret_hash = hashlib.sha256(
                (metadata["webui_token"] + ".napcat").encode()
            ).hexdigest()
            login = urllib.request.Request(
                f"{base}/auth/login",
                data=json.dumps({"hash": secret_hash}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(login, timeout=3) as response:
                login_result = json.load(response)
            if login_result.get("code") != 0:
                raise RuntimeError(
                    str(login_result.get("message") or "NapCat WebUI 鉴权失败")
                )
            credential = login_result["data"]["Credential"]
            self._credentials[ref] = (credential, time.monotonic() + 3000)
        else:
            credential = cached[0]
        request = urllib.request.Request(
            f"{base}/QQLogin/{route}",
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {credential}",
            },
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            result = json.load(response)
        if result.get("code") != 0:
            raise RuntimeError(str(result.get("message") or "NapCat WebUI 请求失败"))
        return result.get("data")

    async def login_status(self, ref: str) -> dict[str, Any]:
        """Reads QR and authentication state from the official WebUI."""
        try:
            async with self._locks.setdefault(ref, asyncio.Lock()):
                data = await asyncio.to_thread(
                    self._request, ref, "CheckLoginStatus", {}
                )
        except (OSError, KeyError, ValueError) as exc:
            return {"phase": "starting", "qrcode": "", "error": str(exc)}
        return {
            "phase": "online" if data.get("isLogin") else "login_required",
            "qrcode": str(data.get("qrcodeurl") or ""),
            "error": str(data.get("loginError") or ""),
            "login_phase": str(data.get("loginPhase") or ""),
        }

    async def refresh_qrcode(self, ref: str) -> dict[str, Any]:
        """Requests a new QR code for this managed instance."""
        async with self._locks.setdefault(ref, asyncio.Lock()):
            data = await asyncio.to_thread(self._request, ref, "RefreshQRcode", {})
        return {
            "qrcode": str(data.get("qrcodeurl") or ""),
            "restarting": bool(data.get("restarting")),
        }
