"""Independent plugin setup and configuration contracts."""

from pathlib import Path
import pytest
from shiori_sdk.testing.service_context import FakeServiceContext
from plugins.browser_use.backend.plugin import setup

PACKAGE_DIR = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "config,prefix,count",
    [({}, "agent_browser_", 28), ({"backend": "ego(lite)"}, "ego_browser_", 8)],
)
async def test_setup_is_lazy_and_unload_retires_retained_tools(
    tmp_path, config, prefix, count
):
    context = FakeServiceContext(
        "browser_use", tmp_path, config=config, package_dir=PACKAGE_DIR
    )
    await setup(context.as_capability())
    tool = context.tools.get_tool(prefix + "snapshot")
    assert tool is not None and len(context.tools.tools) == count
    assert all(name.startswith(prefix) for name in context.tools.tools)
    await context.aclose()
    with pytest.raises(RuntimeError, match="已停用"):
        await tool.execute(role_id="mira")


def test_config_schema_labels_fields_for_the_settings_form() -> None:
    from plugins.browser_use.backend.config import BrowserUseConfig

    properties = BrowserUseConfig.model_json_schema()["properties"]
    assert properties["headed"]["title"] == "显示浏览器窗口（agent-browser）"
    assert properties["timeout_seconds"]["title"] == "单次操作超时"
    assert properties["timeout_seconds"]["unit"] == "秒"
