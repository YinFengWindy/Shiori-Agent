"""tool_loop_guard 的 ``plugin.config.get``/``plugin.config.set`` 契约（#239 AC5）。

迁移前 tool_loop_guard 没有声明 config_model，写配置会直接被拒绝
(``plugin_config_unsupported``，见 test_plugin_config.py 里 qqbot/hello 的
对照用例)，非法的 repeat_limit 也只会被 setup() 里的 ``try/except int()``
静默改写成默认值。这里证明：声明 config_model 之后，读写通道真的打通了，
且非法值在配置边界被拒绝并给出诊断，而不是被静默改写、也不写盘。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agent.config import load_config_text
from bootstrap.app import AppRuntime, RuntimeFeatures
from core.roles.store import RoleStore
from desktop_bridge.runtime.service import ReloadableDesktopService

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_TOOL_LOOP_GUARD_PLUGIN_DIR = _REPOSITORY_ROOT / "plugins" / "tool_loop_guard"


def _config() -> str:
    return (
        "[llm]\nregistrations = []\n"
        "\n[agent.maintenance]\nmemory_optimizer_enabled = false\n"
        '\n[proactive]\nenabled = false\nprofile = "quiet"\n'
    )


def _stage_plugin_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "plugin_dirs"
    shutil.copytree(_TOOL_LOOP_GUARD_PLUGIN_DIR, root / "tool_loop_guard")
    monkeypatch.setattr(
        "bootstrap.tools._resolve_plugin_dirs", lambda workspace: [root]
    )


async def _start_service(
    tmp_path: Path,
) -> tuple[ReloadableDesktopService, Path, AppRuntime]:
    config_text = _config()
    path = tmp_path / "config.toml"
    path.write_text(config_text, encoding="utf-8")
    app = AppRuntime(
        load_config_text(config_text),
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    service = ReloadableDesktopService(app, path, RoleStore(tmp_path))
    return service, path, app


async def _request(service: ReloadableDesktopService, method: str, payload=None):
    return await service.handle(
        {"id": method, "method": method, "payload": payload or {}},
        emit_event=lambda event: None,
    )


@pytest.mark.asyncio
async def test_get_returns_schema_and_the_default_repeat_limit(tmp_path, monkeypatch):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, _, app = await _start_service(tmp_path)
    try:
        response = await _request(
            service, "plugin.config.get", {"plugin_id": "tool_loop_guard"}
        )

        assert response.error is None, response.error
        assert response.payload["schema"]["title"] == "ToolLoopGuardConfig"
        # 未写入过配置：值来自模型默认值补全，迁移前后默认值都必须是 3。
        assert response.payload["values"]["repeat_limit"] == 3
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_set_validates_persists_and_survives_a_restart(tmp_path, monkeypatch):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        response = await _request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "tool_loop_guard",
                "operation_id": "op-valid",
                "values": {"repeat_limit": 5},
            },
        )

        assert response.error is None, response.error
        assert response.payload["values"]["repeat_limit"] == 5

        on_disk = path.read_text(encoding="utf-8")
        assert "repeat_limit = 5" in on_disk

        after = await _request(
            service, "plugin.config.get", {"plugin_id": "tool_loop_guard"}
        )
        assert after.payload["values"]["repeat_limit"] == 5
    finally:
        await service.aclose()
        await app.shutdown()

    restarted = load_config_text(path.read_text(encoding="utf-8"))
    assert restarted.plugins["tool_loop_guard"]["repeat_limit"] == 5


@pytest.mark.asyncio
async def test_set_rejects_repeat_limit_below_the_floor_and_writes_nothing(
    tmp_path, monkeypatch
):
    """repeat_limit 的下限是 2（沿用迁移前 ``max(2, int(raw_limit))`` 的语义）：
    1 必须在配置边界被拒绝，磁盘文件一个字节都不能改。"""
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        before = path.read_text(encoding="utf-8")

        response = await _request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "tool_loop_guard",
                "operation_id": "op-invalid",
                "values": {"repeat_limit": 1},
            },
        )

        assert response.error is not None
        assert response.error.code == "plugin_config_invalid"
        assert path.read_text(encoding="utf-8") == before
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_set_rejects_a_non_integer_repeat_limit_and_writes_nothing(
    tmp_path, monkeypatch
):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        before = path.read_text(encoding="utf-8")

        response = await _request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "tool_loop_guard",
                "operation_id": "op-invalid-type",
                "values": {"repeat_limit": "abc"},
            },
        )

        assert response.error is not None
        assert response.error.code == "plugin_config_invalid"
        assert path.read_text(encoding="utf-8") == before
    finally:
        await service.aclose()
        await app.shutdown()
