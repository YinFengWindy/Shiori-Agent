"""Owned NapCat processes for private QQ account instances."""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
from pathlib import Path
from typing import Any

from .napcat_account_files import NapCatAccountFiles
from .napcat_installer import NapCatInstaller
from .napcat_qrcode import NapCatQrCache
from .napcat_webui import NapCatWebUi


class ManagedNapCat(NapCatInstaller):
    """Starts and stops only plugin-owned per-account NapCat processes."""

    def __init__(self, data_dir: Path) -> None:
        super().__init__(data_dir)
        self._files = NapCatAccountFiles(self.root)
        self._qr = NapCatQrCache(self._files.account_dir)
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._webui = NapCatWebUi(self._files.metadata)

    def endpoint(self, ref: str) -> tuple[str, str]:
        """Returns a stable private OneBot endpoint for a managed account."""
        return self._files.endpoint(ref)

    async def start(self, ref: str, expected_uin: str) -> None:
        """Starts one owned process with private profile and NapCat directories."""
        process = self._processes.get(ref)
        if process is not None and process.poll() is None:
            return
        await self.prepare()
        self._files.write_configs(ref, expected_uin)
        self._qr.clear(ref)
        account_dir = self._files.account_dir(ref)
        profile = self._files.prepare_profile(ref)
        metadata = self._files.metadata(ref)
        for port in (metadata["webui_port"], metadata["onebot_port"]):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                try:
                    listener.bind(("127.0.0.1", port))
                except OSError as exc:
                    raise RuntimeError(f"托管 NapCat 端口 {port} 已被占用") from exc
        inherited = {
            key: value
            for key, value in os.environ.items()
            if key
            not in {
                "NAPCAT_QUICK_ACCOUNT",
                "NAPCAT_QUICK_PASSWORD",
                "NAPCAT_QUICK_PASSWORD_MD5",
            }
        }
        environment = {
            **inherited,
            "USERPROFILE": str(profile),
            "HOME": str(profile),
            "APPDATA": str(profile / "AppData" / "Roaming"),
            "LOCALAPPDATA": str(profile / "AppData" / "Local"),
            "TEMP": str(profile / "Temp"),
            "TMP": str(profile / "Temp"),
            "PATH": str(self.install_dir) + os.pathsep + os.environ.get("PATH", ""),
            "NAPCAT_WORKDIR": str(account_dir / "napcat"),
            "NAPCAT_WEBUI_PREFERRED_PORT": str(metadata["webui_port"]),
            "NAPCAT_WEBUI_SECRET_KEY": metadata["webui_token"],
            "NAPCAT_WEBUI_JWT_SECRET_KEY": metadata["webui_token"],
        }
        if expected_uin:
            environment["NAPCAT_QUICK_ACCOUNT"] = expected_uin
        self._webui.reset(ref)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        log = (account_dir / "process.log").open("ab")
        try:
            self._processes[ref] = subprocess.Popen(
                [
                    str(self.install_dir / "node.exe"),
                    str(self.install_dir / "index.js"),
                ],
                cwd=account_dir,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=flags,
            )
        finally:
            log.close()

    async def stop(self, ref: str) -> None:
        """Terminates only the process launched for this account."""
        process = self._processes.pop(ref, None)
        self._qr.clear(ref)
        self._webui.reset(ref)
        if process is None or process.poll() is not None:
            return
        if os.name == "nt":
            await asyncio.to_thread(
                subprocess.run,
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            process.terminate()
        try:
            await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=10)
        except TimeoutError:
            process.kill()
            await asyncio.to_thread(process.wait)

    async def stop_all(self) -> None:
        """Stops owned processes without changing saved login sessions."""
        await asyncio.gather(*(self.stop(ref) for ref in list(self._processes)))

    async def logout(self, ref: str) -> None:
        """Stops QQ and removes only this account's native login session data."""
        await self.stop(ref)
        await asyncio.to_thread(self._files.clear_login_data, ref)

    async def login_status(self, ref: str) -> dict[str, Any]:
        """Exposes the official QR image only while this account needs login."""
        process = self._processes.get(ref)
        if process is None or process.poll() is not None:
            return {"phase": "stopped", "qrcode": "", "error": "NapCat 未运行"}
        status = await self._webui.login_status(ref)
        scan_url = status["qrcode"]
        if status["phase"] == "login_required" and scan_url:
            status["qrcode"] = self._qr.image_uri(ref, scan_url)
        else:
            if status["phase"] in {"online", "login_required"}:
                self._qr.clear(ref)
            status["qrcode"] = ""
        return status

    async def refresh_qrcode(self, ref: str) -> dict[str, Any]:
        """Waits for a distinct official PNG after refreshing the scan URL."""
        previous_url = self._qr.scan_url(ref)
        previous_digest = self._qr.digest(ref)
        result = await self._webui.refresh_qrcode(ref)
        scan_url = result["qrcode"]
        if result["restarting"]:
            self._qr.clear(ref)
            return {"qrcode": "", "restarting": True}
        if not scan_url or scan_url == previous_url:
            raise RuntimeError("NapCat 未返回新的登录二维码")
        for _ in range(30):
            image = self._qr.image_uri(ref, scan_url, reject_digest=previous_digest)
            if image:
                return {"qrcode": image, "restarting": False}
            await asyncio.sleep(0.1)
        raise RuntimeError("NapCat 新二维码图片缺失或仍是旧图")
