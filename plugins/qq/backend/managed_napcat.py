"""Private per-account NapCat processes and QQ login data."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

from infra.persistence.json_store import atomic_save_json
from .napcat_installer import NapCatInstaller
from .napcat_webui import NapCatWebUi


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class ManagedNapCat(NapCatInstaller):
    """Owns downloaded binaries and processes; never attaches to external NapCat."""

    def __init__(self, data_dir: Path) -> None:
        super().__init__(data_dir)
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._webui = NapCatWebUi(self._metadata)

    def _account_dir(self, ref: str) -> Path:
        if ref != "legacy" and (
            not ref or any(char not in "0123456789abcdef" for char in ref)
        ):
            raise ValueError("托管账号引用无效")
        return self.root / "accounts" / ref

    def _reserved_ports(self) -> set[int]:
        reserved: set[int] = set()
        accounts_dir = self.root / "accounts"
        if not accounts_dir.exists():
            return reserved
        for path in accounts_dir.glob("*/runtime.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            reserved.update((int(data["webui_port"]), int(data["onebot_port"])))
        return reserved

    def _metadata(self, ref: str) -> dict[str, Any]:
        path = self._account_dir(ref) / "runtime.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        reserved = self._reserved_ports()
        webui_port = _free_port()
        while webui_port in reserved:
            webui_port = _free_port()
        reserved.add(webui_port)
        onebot_port = _free_port()
        while onebot_port in reserved:
            onebot_port = _free_port()
        metadata = {
            "webui_port": webui_port,
            "onebot_port": onebot_port,
            "webui_token": uuid4().hex,
            "onebot_token": uuid4().hex,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_save_json(path, metadata)
        return metadata

    def endpoint(self, ref: str) -> tuple[str, str]:
        """Returns the private OneBot URL and credential for a managed account."""
        metadata = self._metadata(ref)
        return f"ws://127.0.0.1:{metadata['onebot_port']}", metadata["onebot_token"]

    def _write_onebot_config(self, ref: str, expected_uin: str) -> None:
        metadata = self._metadata(ref)
        config_dir = self._account_dir(ref) / "napcat" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        content = {
            "network": {
                "websocketServers": [
                    {
                        "name": "shiori",
                        "enable": True,
                        "host": "127.0.0.1",
                        "port": metadata["onebot_port"],
                        "messagePostFormat": "array",
                        "reportSelfMessage": False,
                        "token": metadata["onebot_token"],
                    }
                ]
            }
        }
        atomic_save_json(config_dir / "onebot11.json", content)
        if expected_uin:
            atomic_save_json(config_dir / f"onebot11_{expected_uin}.json", content)
        webui_config = config_dir / "webui.json"
        existing = (
            json.loads(webui_config.read_text(encoding="utf-8"))
            if webui_config.exists()
            else {}
        )
        atomic_save_json(
            webui_config,
            {
                **existing,
                "host": "127.0.0.1",
                "port": metadata["webui_port"],
                "token": metadata["webui_token"],
            },
        )

    def _check_native_dependencies(self) -> None:
        missing = [
            name
            for name in ("crypto.dll", "ssl.dll")
            if not (self.install_dir / name).is_file() and shutil.which(name) is None
        ]
        if missing:
            raise RuntimeError(
                "NapCat 官方 Windows Node 包缺少原生 QQ 依赖: " + ", ".join(missing)
            )

    async def start(self, ref: str, expected_uin: str) -> None:
        """Starts one owned process with private profile and NapCat directories."""
        process = self._processes.get(ref)
        if process is not None and process.poll() is None:
            return
        await self.prepare()
        self._check_native_dependencies()
        self._write_onebot_config(ref, expected_uin)
        account_dir = self._account_dir(ref)
        profile = account_dir / "profile"
        for directory in (
            profile,
            profile / "AppData" / "Roaming",
            profile / "AppData" / "Local",
            profile / "Temp",
        ):
            directory.mkdir(parents=True, exist_ok=True)
        metadata = self._metadata(ref)
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
        self._webui.reset(ref)

    async def stop_all(self) -> None:
        """Stops owned processes without changing saved login sessions."""
        await asyncio.gather(*(self.stop(ref) for ref in list(self._processes)))

    async def logout(self, ref: str) -> None:
        """Stops QQ and removes only this account's native login session data."""
        await self.stop(ref)
        profile = self._account_dir(ref) / "profile"
        for relative in (
            Path("AppData/Roaming/Tencent/QQNT"),
            Path("AppData/Local/Tencent/QQNT"),
            Path("AppData/Roaming/QQ"),
            Path("AppData/Local/QQ"),
            Path(".config/QQ"),
        ):
            directory = profile / relative
            if directory.exists():
                await asyncio.to_thread(shutil.rmtree, directory)

    async def login_status(self, ref: str) -> dict[str, Any]:
        """Reads QR and authentication state from this instance's official WebUI."""
        process = self._processes.get(ref)
        if process is None or process.poll() is not None:
            return {"phase": "stopped", "qrcode": "", "error": "NapCat 未运行"}
        return await self._webui.login_status(ref)

    async def refresh_qrcode(self, ref: str) -> dict[str, Any]:
        """Requests a new QR code for a running managed instance."""
        return await self._webui.refresh_qrcode(ref)
