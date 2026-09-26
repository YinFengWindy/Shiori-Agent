"""Private account ports and OneBot configuration files."""

from __future__ import annotations

import json

from plugins.qq.backend.napcat_account_files import NapCatAccountFiles


def test_config_and_ports_are_isolated_by_account(tmp_path):
    files = NapCatAccountFiles(tmp_path)
    first = "a" * 32
    second = "b" * 32
    files.write_configs(first, "101")
    files.write_configs(second, "202")
    a = files.metadata(first)
    b = files.metadata(second)
    assert (
        len({a["webui_port"], a["onebot_port"], b["webui_port"], b["onebot_port"]}) == 4
    )
    config = json.loads(
        (files.account_dir(first) / "napcat/config/onebot11.json").read_text(
            encoding="utf-8"
        )
    )
    assert config["network"]["websocketServers"][0]["token"] == a["onebot_token"]
    assert (files.account_dir(first) / "napcat/config/onebot11_101.json").is_file()
    assert not (files.account_dir(second) / "napcat/config/onebot11_101.json").exists()
