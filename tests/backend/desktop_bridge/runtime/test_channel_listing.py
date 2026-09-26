"""channels.list：desktop 与插件声明渠道在四种状态下的请求级行为。"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agent.config import load_config_text
from bootstrap.app import AppRuntime, RuntimeFeatures
from core.roles.store import RoleStore
from desktop_bridge.runtime.service import ReloadableDesktopService

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_QQBOT_PLUGIN_DIR = _REPOSITORY_ROOT / "plugins" / "qqbot"
_TELEGRAM_PLUGIN_DIR = _REPOSITORY_ROOT / "plugins" / "telegram"
_QQ_PLUGIN_DIR = _REPOSITORY_ROOT / "plugins" / "qq"

# 不联网的渠道插件：配置 fail = true 时启动失败，用来覆盖 active/failed。
_FAKE_CHANNEL_PLUGIN_PY = """
class _Channel:
    name = "fake"

    def __init__(self, fail):
        self._fail = fail

    async def start(self, ctx):
        if self._fail:
            raise ConnectionError("gateway refused")

    async def stop(self):
        pass

    def pause_intake(self):
        pass

    def resume_intake(self):
        pass

    def status(self):
        return {"connected": True, "account": "fake-bot"}


async def setup(ctx):
    ctx.channels.add(_Channel(bool(ctx.config.as_dict().get("fail"))))
""".strip()


def _write_fake_channel_plugin(root: Path, plugin_id: str) -> None:
    package = root / plugin_id
    (package / "backend").mkdir(parents=True)
    (package / "backend" / "plugin.py").write_text(
        _FAKE_CHANNEL_PLUGIN_PY, encoding="utf-8"
    )
    (package / "manifest.yaml").write_text(
        f"api: 2\nid: {plugin_id}\ncapabilities: [config, channels]\nchannels:\n"
        "  - {name: fake, label: Fake, contact_label: Fake 用户 ID, chat_types:"
        " [{type: private, label: 私聊, chat_id_label: 用户 ID}]}\n",
        encoding="utf-8",
    )


async def _list_channels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: str = "",
    *,
    fake_plugins: tuple[str, ...] = (),
) -> dict[str, dict]:
    root = tmp_path / "plugin_dirs"
    shutil.copytree(_QQBOT_PLUGIN_DIR, root / "qqbot")
    shutil.copytree(_TELEGRAM_PLUGIN_DIR, root / "telegram")
    shutil.copytree(_QQ_PLUGIN_DIR, root / "qq")
    for plugin_id in fake_plugins:
        _write_fake_channel_plugin(root, plugin_id)
    monkeypatch.setattr(
        "bootstrap.tools._resolve_plugin_dirs", lambda workspace: [root]
    )
    text = (
        "[llm]\nregistrations = []\n\n[agent.maintenance]\n"
        "memory_optimizer_enabled = false\n\n" + config
    )
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    app = AppRuntime(
        load_config_text(text),
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=True, enable_proactive=False),
    )
    await app.start()
    service = ReloadableDesktopService(app, path, RoleStore(tmp_path))
    try:
        response = await service.handle(
            {"id": "channels", "method": "channels.list", "payload": {}},
            emit_event=lambda event: None,
        )
    finally:
        await service.aclose()
        await app.shutdown()
    assert response.error is None, response.error
    rows = response.payload["channels"]
    assert rows[0]["name"] == "desktop"
    assert len({row["name"] for row in rows}) == len(rows)
    return {row["name"]: row for row in rows}


@pytest.mark.asyncio
async def test_lists_desktop_builtins_and_account_ready_qqbot(tmp_path, monkeypatch):
    rows = await _list_channels(tmp_path, monkeypatch)
    assert list(rows) == ["desktop", "qq", "qqbot", "telegram"]
    assert rows["desktop"]["state"] == "active"
    # Telegram、QQ 都已迁为插件：同名渠道由插件声明提供，不再有内置行（#363 T4/T5）。
    assert rows["qq"]["plugin_id"] == "qq"
    assert rows["qq"]["label"] == "QQ（NapCat）"
    assert rows["qq"]["state"] == "not_configured"
    assert rows["telegram"]["plugin_id"] == "telegram"
    assert rows["telegram"]["label"] == "Telegram"
    assert rows["telegram"]["state"] == "not_configured"
    assert rows["qqbot"] == {
        "name": "qqbot",
        "label": "QQBot",
        "contact_label": None,
        "chat_types": [
            {
                "type": "private",
                "label": "私聊",
                "chat_id_label": "用户 OpenID",
                "chat_id_hint": "对方的用户 OpenID",
                "prefix": "c2c:",
            }
        ],
        "plugin_id": "qqbot",
        "plugin_enabled": True,
        "state": "active",
        "error": "",
        "status": None,
    }


@pytest.mark.asyncio
async def test_disabled_plugin_channel_stays_listed(tmp_path, monkeypatch):
    rows = await _list_channels(
        tmp_path, monkeypatch, "[plugins.qqbot]\nenabled = false\n"
    )
    assert rows["qqbot"]["plugin_enabled"] is False
    assert rows["qqbot"]["state"] == "plugin_disabled"


@pytest.mark.asyncio
async def test_disabled_migrated_channel_plugins_keep_their_channels_listed(
    tmp_path, monkeypatch
):
    rows = await _list_channels(
        tmp_path,
        monkeypatch,
        "[plugins.telegram]\nenabled = false\n\n[plugins.qq]\nenabled = false\n",
    )
    for name in ("telegram", "qq"):
        assert rows[name]["plugin_id"] == name
        assert rows[name]["state"] == "plugin_disabled"


@pytest.mark.asyncio
async def test_active_plugin_channel_reports_its_status(tmp_path, monkeypatch):
    rows = await _list_channels(tmp_path, monkeypatch, fake_plugins=("fake",))
    assert rows["fake"]["plugin_id"] == "fake"
    assert rows["fake"]["state"] == "active"
    assert rows["fake"]["error"] == ""
    assert rows["fake"]["status"] == {"connected": True, "account": "fake-bot"}


@pytest.mark.asyncio
async def test_channel_start_failure_is_exposed(tmp_path, monkeypatch):
    rows = await _list_channels(
        tmp_path, monkeypatch, "[plugins.fake]\nfail = true\n", fake_plugins=("fake",)
    )
    assert rows["fake"]["state"] == "failed"
    assert rows["fake"]["error"] == "start: ConnectionError: gateway refused"


@pytest.mark.asyncio
async def test_conflicting_declarations_list_one_failed_channel(tmp_path, monkeypatch):
    rows = await _list_channels(
        tmp_path, monkeypatch, fake_plugins=("fake", "fake_copy")
    )
    assert rows["fake"]["state"] == "failed"
    assert "fake_copy" in rows["fake"]["error"]
