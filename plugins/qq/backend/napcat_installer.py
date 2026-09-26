"""Pinned official Windows NapCat installation in plugin-private storage."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import shutil
import urllib.request
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from infra.persistence.json_store import atomic_save_json

VERSION = "v4.18.28"
ARCHIVE_SHA256 = "fb64fa3b036ad2df1a5d7c204c482694c20e4b763978c8a4968fd3474c05b4a8"
ARCHIVE_URL = (
    f"https://github.com/NapNeko/NapCatQQ/releases/download/{VERSION}/"
    "NapCat.Shell.Windows.Node.zip"
)


def managed_available() -> bool:
    """Whether the pinned official binary can run on this host."""
    return os.name == "nt" and platform.machine().lower() in {"amd64", "x86_64"}


class NapCatInstaller:
    """Publishes only a complete SHA-256 verified installation."""

    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir / "managed-napcat"
        self.install_dir = self.root / VERSION
        self._preparation: dict[str, Any] = {"stage": "idle", "percent": 0}
        self._install_lock = asyncio.Lock()

    def preparation(self) -> dict[str, Any]:
        """Returns the current installer stage without blocking the UI."""
        if self._package_ready():
            try:
                self._check_native_dependencies()
            except RuntimeError as exc:
                return {
                    "stage": "error",
                    "percent": 0,
                    "version": VERSION,
                    "error": str(exc),
                }
            return {"stage": "ready", "percent": 100, "version": VERSION}
        return {**self._preparation, "version": VERSION}

    def _package_ready(self) -> bool:
        marker = self.install_dir / "shiori-install.json"
        if not marker.is_file():
            return False
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return False
        return (
            data == {"version": VERSION, "sha256": ARCHIVE_SHA256}
            and (self.install_dir / "node.exe").is_file()
            and (self.install_dir / "index.js").is_file()
            and (self.install_dir / "napcat" / "napcat.mjs").is_file()
        )

    async def prepare(self) -> None:
        """Downloads, verifies, and publishes a complete installation atomically."""
        if not managed_available():
            raise RuntimeError("托管 NapCat 仅支持 Windows x64")
        async with self._install_lock:
            try:
                if not self._package_ready():
                    await asyncio.to_thread(self._prepare_sync)
                self._check_native_dependencies()
            except Exception as exc:
                self._preparation = {"stage": "error", "percent": 0, "error": str(exc)}
                raise
            self._preparation = {"stage": "ready", "percent": 100}

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

    def _prepare_sync(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        archive = self.root / f"{VERSION}.zip"
        if not archive.exists() or self._sha256(archive) != ARCHIVE_SHA256:
            part = self.root / f"{VERSION}.zip.part"
            self._preparation = {"stage": "downloading", "percent": 0}
            try:
                with urllib.request.urlopen(ARCHIVE_URL, timeout=30) as response:
                    total = int(response.headers.get("Content-Length") or 0)
                    received = 0
                    with part.open("wb") as output:
                        while chunk := response.read(1024 * 1024):
                            output.write(chunk)
                            received += len(chunk)
                            self._preparation = {
                                "stage": "downloading",
                                "percent": (
                                    min(79, int(received * 80 / total)) if total else 0
                                ),
                            }
                if self._sha256(part) != ARCHIVE_SHA256:
                    raise ValueError("NapCat 下载文件 SHA-256 校验失败")
                part.replace(archive)
            finally:
                part.unlink(missing_ok=True)
        self._preparation = {"stage": "extracting", "percent": 80}
        staging = self.root / f".{VERSION}-{uuid4().hex}"
        try:
            staging.mkdir()
            with zipfile.ZipFile(archive) as bundle:
                for info in bundle.infolist():
                    destination = (staging / info.filename).resolve()
                    if not destination.is_relative_to(staging.resolve()):
                        raise ValueError("NapCat 压缩包包含非法路径")
                    if info.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with (
                            bundle.open(info) as source,
                            destination.open("wb") as target,
                        ):
                            shutil.copyfileobj(source, target)
            for required in ("node.exe", "index.js", "napcat/napcat.mjs"):
                if not (staging / required).is_file():
                    raise ValueError(f"NapCat 安装包缺少 {required}")
            atomic_save_json(
                staging / "shiori-install.json",
                {"version": VERSION, "sha256": ARCHIVE_SHA256},
            )
            if self.install_dir.exists():
                shutil.rmtree(self.install_dir)
            staging.replace(self.install_dir)
            self._preparation = {"stage": "verifying", "percent": 99}
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
