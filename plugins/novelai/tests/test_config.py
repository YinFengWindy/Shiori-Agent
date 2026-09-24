"""NovelAI configuration through the real plugin settings channel."""

import pytest

from agent.config import load_config_text
from shiori_plugin_testkit.bridge import plugin_bridge_request


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled_line", ["", "enabled = true\n"])
async def test_novelai_config_round_trip_preserves_host_enablement(
    plugin_runtime, enabled_line
):
    """Saving NovelAI settings must not recreate the duplicate enable switch."""
    config_text = "\n[plugins.novelai]\n" + enabled_line + 'token = "test-token"\n'
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
        assert stored.get("enabled", True) is True

        listed = await plugin_bridge_request(service, "plugins.list")
        novelai = next(
            item for item in listed.payload["plugins"] if item["id"] == "novelai"
        )
        assert novelai["enabled"] is True
        assert novelai["state"] == "ACTIVE"


def test_config_schema_labels_every_field_for_the_settings_form():
    from plugins.novelai.backend.config import NovelAIConfig

    properties = NovelAIConfig.model_json_schema()["properties"]
    for key, item in properties.items():
        # pydantic's generated fallback title ("Nsfw Model") must never surface.
        assert item["title"] != key.replace("_", " ").title(), key
    assert properties["max_steps"]["unit"] == "步"
