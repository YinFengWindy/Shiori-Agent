"""Independent plugin setup and configuration contracts."""

import pytest
from shiori_sdk.testing.service_context import FakeServiceContext
from plugins.browser_use.backend.plugin import setup


async def test_setup_is_lazy_and_unload_retires_retained_tools(tmp_path):
    context = FakeServiceContext("browser_use", tmp_path)
    await setup(context.as_capability())
    tool = context.tools.get_tool("agent_browser_snapshot")
    assert tool is not None and len(context.tools.tools) == 28
    await context.aclose()
    with pytest.raises(RuntimeError, match="已停用"):
        await tool.execute(role_id="mira")


def test_config_schema_labels_fields_for_the_settings_form() -> None:
    from plugins.browser_use.backend.config import BrowserUseConfig

    properties = BrowserUseConfig.model_json_schema()["properties"]
    assert properties["headed"]["title"] == "显示浏览器窗口"
    assert properties["timeout_seconds"]["title"] == "单次操作超时"
    assert properties["timeout_seconds"]["unit"] == "秒"
