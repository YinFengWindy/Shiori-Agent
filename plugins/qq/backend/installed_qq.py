"""Locate one validated Tencent QQ runtime required by pinned Windows NapCat."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

QQ_VERSION = "9.9.31-49738"
_EXPECTED_SHA256 = {
    "crypto.dll": "2a143d944cd80ba373242deacd06ad47523c07191a4a322e4336e62062d2f5f3",
    "ssl.dll": "fbadd7a295e8d932295c5b59c086b1a9074f61f347694674b4c76ecff5c5965c",
    "wrapper.node": "a1e59891e743c271d641ee011f47aa887d9f7dfae6b3bb9292a03af759dec203",
}
_UNINSTALL_KEYS = (
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QQ",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\QQ",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _install_root() -> Path:
    if os.name != "nt":
        raise RuntimeError("托管 NapCat 仅支持 Windows x64")
    import winreg

    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for key_name in _UNINSTALL_KEYS:
            try:
                with winreg.OpenKey(hive, key_name) as key:
                    uninstall, _ = winreg.QueryValueEx(key, "UninstallString")
            except (FileNotFoundError, OSError):
                continue
            if not isinstance(uninstall, str):
                continue
            executable = Path(uninstall.strip().strip('"'))
            if (
                not executable.is_absolute()
                or executable.name.lower() != "uninstall.exe"
                or not executable.is_file()
                or not (executable.parent / "QQ.exe").is_file()
            ):
                continue
            return executable.parent
    raise RuntimeError(f"未找到官方 QQ {QQ_VERSION} 安装目录（Windows 卸载注册表）")


def resolve_official_qq(napcat_dir: Path) -> Path:
    """Validates the installed QQ build and returns its native DLL directory."""
    bundled_wrapper = napcat_dir / "wrapper.node"
    if (
        not bundled_wrapper.is_file()
        or _sha256(bundled_wrapper) != _EXPECTED_SHA256["wrapper.node"]
    ):
        raise RuntimeError("NapCat 官方组件 wrapper.node 缺失或摘要不匹配")

    root = _install_root()
    version_config = root / "versions" / "config.json"
    if not version_config.is_file():
        raise RuntimeError("QQ 安装目录缺少 versions/config.json")
    try:
        version = json.loads(version_config.read_text(encoding="utf-8")).get(
            "curVersion"
        )
    except (OSError, ValueError) as exc:
        raise RuntimeError("QQ versions/config.json 无效") from exc
    if version != QQ_VERSION:
        raise RuntimeError(
            f"托管 NapCat 需要 QQ {QQ_VERSION}，当前为 {version or '未知'}"
        )

    app_dir = root / "versions" / QQ_VERSION / "resources" / "app"
    for name, expected in _EXPECTED_SHA256.items():
        file = app_dir / name
        if not file.is_file():
            raise RuntimeError(f"QQ {QQ_VERSION} 缺少 {name}")
        if _sha256(file) != expected:
            raise RuntimeError(f"QQ {QQ_VERSION} 的 {name} 摘要不匹配")
    return app_dir
