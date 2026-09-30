"""Owned NapCat processes for private QQ account instances."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from infra.process.windows_job import WindowsJob

from . import napcat_process_guard as guard
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
        # Kill-on-close jobs make the OS reap each NapCat tree when this bridge
        # dies without running stop_all (crash, kill, hot reload).
        self._jobs: dict[str, WindowsJob] = {}
        self._webui = NapCatWebUi(self._files.metadata)

    def endpoint(self, ref: str) -> tuple[str, str]:
        """Returns a stable private OneBot endpoint for a managed account."""
        return self._files.endpoint(ref)

    def account_refs(self) -> set[str]:
        """Lists private instance directories for startup orphan cleanup."""
        return self._files.refs()

    async def start(self, ref: str, expected_uin: str) -> None:
        """Starts one owned process with private profile and NapCat directories."""
        process = self._processes.get(ref)
        if process is not None and process.poll() is None:
            return
        qq_runtime_dir = await self.prepare()
        self._files.write_configs(ref, expected_uin)
        self._qr.clear(ref)
        account_dir = self._files.account_dir(ref)
        profile = self._files.prepare_profile(ref)
        metadata = self._files.metadata(ref)
        for port in (metadata["webui_port"], metadata["onebot_port"]):
            await self._claim_port(port)
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
            "PATH": os.pathsep.join(
                (str(self.install_dir), str(qq_runtime_dir), os.environ.get("PATH", ""))
            ),
            "NAPCAT_WORKDIR": str(account_dir / "napcat"),
            "NAPCAT_WEBUI_PREFERRED_PORT": str(metadata["webui_port"]),
            "NAPCAT_WEBUI_SECRET_KEY": metadata["webui_token"],
            "NAPCAT_WEBUI_JWT_SECRET_KEY": metadata["webui_token"],
        }
        if expected_uin:
            environment["NAPCAT_QUICK_ACCOUNT"] = expected_uin
        self._webui.reset(ref)
        await self._close_job(ref)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if sys.platform == "win32":
            # Start suspended so node cannot spawn napcat.mjs before joining the job.
            flags |= 0x00000004  # CREATE_SUSPENDED
        log = (account_dir / "process.log").open("ab")
        try:
            process = subprocess.Popen(
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
        if sys.platform == "win32":
            try:
                self._jobs[ref] = WindowsJob(process.pid, resume=True)
            except BaseException:
                process.kill()
                process.wait()
                raise
        self._processes[ref] = process

    async def _claim_port(self, port: int) -> None:
        """Frees a port held by an orphaned tree from this plugin's NapCat install.

        A crashed bridge can leave NapCat alive on the account's persisted ports;
        switching ports is not an option because the orphan still owns the QQ
        profile. Only processes whose image lives under the managed-napcat root
        are killed; any other owner is reported and left untouched.
        """
        if guard.port_bindable(port):
            return
        pid = guard.listener_pid(port)
        owner = guard.process_info(pid) if pid is not None else None
        if owner is None or not self._is_managed(owner):
            detail = (
                f"（PID {owner.pid} {owner.name}）"
                if owner is not None
                else (f"（PID {pid}）" if pid is not None else "")
            )
            raise RuntimeError(f"托管 NapCat 端口 {port} 已被占用{detail}")
        # Climb to the index.js launcher so the whole orphaned tree dies with it.
        root = owner
        while (parent := guard.process_info(root.parent_pid)) is not None and (
            self._is_managed(parent) and parent.create_time <= root.create_time
        ):
            root = parent
        await asyncio.to_thread(guard.kill_process_tree, root.pid)
        for _ in range(50):
            if guard.port_bindable(port):
                return
            await asyncio.sleep(0.1)
        raise RuntimeError(f"托管 NapCat 端口 {port} 在结束残留进程后仍被占用")

    def _is_managed(self, info: guard.ProcessInfo) -> bool:
        """Whether a process image comes from any version under managed-napcat."""
        return info.exe is not None and info.exe.resolve().is_relative_to(
            self.root.resolve()
        )

    async def _close_job(self, ref: str) -> None:
        """Releases this account's job, killing anything still inside it."""
        job = self._jobs.pop(ref, None)
        if job is not None:
            await asyncio.to_thread(job.close)

    async def stop(self, ref: str) -> None:
        """Terminates only the process launched for this account."""
        process = self._processes.pop(ref, None)
        self._qr.clear(ref)
        self._webui.reset(ref)
        try:
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
        finally:
            await self._close_job(ref)

    async def stop_all(self) -> None:
        """Stops owned processes without changing saved login sessions."""
        await asyncio.gather(*(self.stop(ref) for ref in list(self._processes)))

    async def logout(self, ref: str) -> None:
        """Stops QQ and removes only this account's native login session data."""
        await self.stop(ref)
        await asyncio.to_thread(self._files.clear_login_data, ref)

    async def delete(self, ref: str) -> None:
        """Stops QQ and removes every file this account's instance owns."""
        await self.stop(ref)
        await asyncio.to_thread(self._files.remove, ref)

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
