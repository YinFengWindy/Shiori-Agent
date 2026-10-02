"""NovelAI's role draft participant joins the single role commit through the kernel.

The plugin is loaded through the real ``PluginKernel``; drafts go through the
public ``RoleStore.update_role(plugin_drafts=...)`` entry and are read back via
``RoleStore.extensions``. Generic commit atomicity is covered by
``test_extensions.py``; NovelAI's draft schema and pruning rules by
``plugins/novelai/tests/test_role_state.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from shiori_sdk.testing.http import FakeHttp
from shiori_sdk.testing.models import FakeChatProvider
from shiori_sdk.testing.packages import plugin_directory, stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from core.roles.store import RoleStore
from session.manager import SessionManager


async def _load_novelai(tmp_path: Path, roles: RoleStore) -> PluginKernel:
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
            role_store=roles,
            session_manager=SessionManager(tmp_path),
            plugin_configs={"novelai": {"enabled": True, "token": "novel-token"}},
        ),
    )
    await kernel.load_all()
    return kernel


@pytest.mark.asyncio
async def test_invalid_cg_draft_cannot_commit_other_role_edits(tmp_path):
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Before", system_prompt="test")
    kernel = await _load_novelai(tmp_path, roles)
    before = roles.manifest_path.read_bytes()

    with pytest.raises(ValueError, match="autoSceneCgEnabled"):
        roles.update_role(
            "mira",
            name="Rejected",
            plugin_drafts={"novelai": {"autoSceneCgEnabled": "false"}},
        )

    assert roles.manifest_path.read_bytes() == before
    assert await kernel.unload("novelai") == []


@pytest.mark.asyncio
async def test_cg_draft_commits_with_role_save_and_survives_unload(tmp_path):
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Before", system_prompt="test")
    kernel = await _load_novelai(tmp_path, roles)
    assert roles.extensions.project("mira") == {
        "novelai": {"autoSceneCgEnabled": False}
    }

    roles.update_role(
        "mira", name="After", plugin_drafts={"novelai": {"autoSceneCgEnabled": True}}
    )

    role = roles.get_role("mira")
    assert role is not None and role.name == "After"
    assert "auto_scene_cg_enabled" not in role.runtime_config
    assert roles.extensions.project("mira") == {"novelai": {"autoSceneCgEnabled": True}}
    assert await kernel.unload("novelai") == []
    roles.update_role("mira", description="Edited while disabled")
    assert roles.extensions.read("novelai") == {"mira": {"auto_scene_cg_enabled": True}}
