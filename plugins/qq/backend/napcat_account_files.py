"""Persistent NapCat settings and login data owned by one QQ account."""

from __future__ import annotations

import json
import shutil
import socket
from pathlib import Path
from typing import Any
from uuid import uuid4

from infra.persistence.json_store import atomic_save_json


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class NapCatAccountFiles:
    """Keeps each account's ports, configuration, and profile separate."""

    def __init__(self, root: Path) -> None:
        self.root = root / "accounts"

    def account_dir(self, ref: str) -> Path:
        """Resolves only plugin-issued opaque references and the legacy ref."""
        if ref != "legacy" and (
            not ref or any(char not in "0123456789abcdef" for char in ref)
        ):
            raise ValueError("托管账号引用无效")
        return self.root / ref

    def _reserved_ports(self) -> set[int]:
        reserved: set[int] = set()
        if not self.root.exists():
            return reserved
        for path in self.root.glob("*/runtime.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            reserved.update((int(data["webui_port"]), int(data["onebot_port"])))
        return reserved

    def metadata(self, ref: str) -> dict[str, Any]:
        """Returns durable ports and secrets unique across saved accounts."""
        path = self.account_dir(ref) / "runtime.json"
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
        metadata = self.metadata(ref)
        return f"ws://127.0.0.1:{metadata['onebot_port']}", metadata["onebot_token"]

    def write_configs(self, ref: str, expected_uin: str) -> None:
        """Writes the default and known-UIN OneBot settings before startup."""
        metadata = self.metadata(ref)
        config_dir = self.account_dir(ref) / "napcat" / "config"
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

    def prepare_profile(self, ref: str) -> Path:
        """Creates a private Windows profile and temporary directory."""
        profile = self.account_dir(ref) / "profile"
        for directory in (
            profile,
            profile / "AppData" / "Roaming",
            profile / "AppData" / "Local",
            profile / "Temp",
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return profile

    def clear_login_data(self, ref: str) -> None:
        """Removes native QQ sessions only beneath this account's profile."""
        profile = self.account_dir(ref) / "profile"
        for relative in (
            Path("AppData/Roaming/Tencent/QQNT"),
            Path("AppData/Local/Tencent/QQNT"),
            Path("AppData/Roaming/QQ"),
            Path("AppData/Local/QQ"),
            Path(".config/QQ"),
        ):
            directory = profile / relative
            if directory.exists():
                shutil.rmtree(directory)
