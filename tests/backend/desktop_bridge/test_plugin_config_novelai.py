"""NovelAI configuration through the real plugin settings channel."""

import pytest

from agent.config import load_config_text
from shiori_sdk.testing.bridge import plugin_bridge_request


@pytest.mark.asyncio
async def test_novelai_config_round_trip_preserves_host_enablement(
    plugin_runtime,
):
    """Saving NovelAI settings must not recreate the duplicate enable switch."""
    config_text = '\n[plugins.novelai]\nenabled = true\ntoken = "test-token"\n'
    async with plugin_runtime(("novelai",), config_text) as (service, path):
        before = await plugin_bridge_request(
            service, "plugin.config.get", {"plugin_id": "novelai"}
        )
        assert before.error is None, before.error
        assert "enabled" not in before.payload["schema"]["properties"]
        assert "enabled" not in before.payload["values"]

        saved = await plugin_bridge_request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "novelai",
                "operation_id": "save-novelai",
                "values": {**before.payload["values"], "nsfw_enabled": True},
            },
        )
        assert saved.error is None, saved.error
        after = await plugin_bridge_request(
            service, "plugin.config.get", {"plugin_id": "novelai"}
        )
        assert after.error is None, after.error
        assert after.payload["values"] == saved.payload["values"]
        assert after.payload["values"]["nsfw_enabled"] is True
        stored = load_config_text(path.read_text(encoding="utf-8")).plugins["novelai"]
        assert stored["enabled"] is True

        listed = await plugin_bridge_request(service, "plugins.list")
        novelai = next(
            item for item in listed.payload["plugins"] if item["id"] == "novelai"
        )
        assert novelai["enabled"] is True
        assert novelai["state"] == "ACTIVE"


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled_line", ["", "enabled = false\n"])
async def test_disabled_novelai_config_cannot_be_saved_or_enable_the_plugin(
    plugin_runtime, enabled_line
):
    """Disabled plugins keep their stored values without exposing a writable schema."""
    config_text = "\n[plugins.novelai]\n" + enabled_line + 'token = "test-token"\n'
    async with plugin_runtime(("novelai",), config_text) as (service, path):
        original = path.read_bytes()
        before = await plugin_bridge_request(
            service, "plugin.config.get", {"plugin_id": "novelai"}
        )
        assert before.error is None, before.error
        assert before.payload["schema"] is None
        assert before.payload["values"] == {"token": "test-token"}

        saved = await plugin_bridge_request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "novelai",
                "operation_id": "save-disabled-novelai",
                "values": {"token": "changed-token"},
            },
        )
        assert saved.error is not None
        assert saved.error.code == "plugin_config_unsupported"
        assert path.read_bytes() == original
        listed = await plugin_bridge_request(service, "plugins.list")
        assert listed.error is None, listed.error
        novelai = next(
            item for item in listed.payload["plugins"] if item["id"] == "novelai"
        )
        assert novelai["enabled"] is False
        assert novelai["state"] == "DISABLED"
