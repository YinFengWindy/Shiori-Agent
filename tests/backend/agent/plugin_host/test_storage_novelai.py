"""Host private-storage migration carries NovelAI's legacy generations on load.

The plugin is loaded through the real ``PluginKernel`` with the real host
``PluginStorage``; results are read back through ``plugin.novelai.history``.
Record normalization rules live in ``plugins/novelai/tests/test_storage.py`` and
directory copy semantics in ``test_data_migration.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from shiori_sdk.testing.http import FakeHttp
from shiori_sdk.testing.models import FakeChatProvider
from shiori_sdk.testing.packages import plugin_directory, stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from core.roles.store import RoleStore
from session.manager import SessionManager


async def _history(kernel: PluginKernel) -> list[dict[str, Any]]:
    resolved = kernel.rpc.resolve("plugin.novelai.history")
    assert resolved is not None
    _, handler = resolved
    payload = await handler({"limit": 5})
    assert payload is not None
    return payload["records"]


@pytest.mark.asyncio
async def test_loading_novelai_migrates_legacy_generations_and_keeps_identity(
    tmp_path: Path,
):
    old = tmp_path / "private_runtime/novelai"
    output = old / "outputs/record/output.png"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"image")
    record = {"id": "record", "output_paths": [str(output)], "base_image_path": ""}
    (old / "records.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    (output.parent / "meta.json").write_text(json.dumps(record), encoding="utf-8")
    (output.parent / "request.json").write_text(
        '{"parameters":{"seed":12}}', encoding="utf-8"
    )
    stage_plugin_package(plugin_directory("novelai"), tmp_path / "plugins/novelai")
    kernel = PluginKernel(
        [tmp_path / "plugins"],
        services=HostServices(
            http=FakeHttp(),
            light_provider=FakeChatProvider(),
            light_model="light",
            event_bus=EventBus(),
            tool_registry=ToolRegistry(),
            workspace=tmp_path,
            role_store=RoleStore(tmp_path),
            session_manager=SessionManager(tmp_path),
            plugin_configs={"novelai": {"enabled": True, "token": "novel-token"}},
        ),
    )
    await kernel.load_all()

    [migrated] = await _history(kernel)
    assert migrated["original_output_paths"] == [str(output)]
    [moved] = migrated["output_paths"]
    assert moved != str(output)
    assert Path(moved).read_bytes() == b"image"
    assert (Path(moved).parent / "request.json").read_text(
        encoding="utf-8"
    ) == '{"parameters":{"seed":12}}'
    assert output.is_file()

    assert await kernel.unload("novelai") == []
    await kernel.load_all()
    assert await _history(kernel) == [migrated]
    assert await kernel.unload("novelai") == []
