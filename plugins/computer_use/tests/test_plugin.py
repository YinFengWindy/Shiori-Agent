"""Independent plugin setup and configuration contracts."""

import pytest
from shiori_sdk.testing.service_context import FakeServiceContext
from plugins.computer_use.backend.plugin import setup


async def test_setup_is_lazy_and_unload_retires_retained_tools(tmp_path):
    context = FakeServiceContext("computer_use", tmp_path)
    await setup(context.as_capability())
    tool = context.tools.get_tool("computer_get_window_state")
    assert tool is not None
    await context.aclose()
    with pytest.raises(RuntimeError, match="已停用"):
        await tool.execute(role_id="mira", pid=1, window_id=1)


def test_config_schema_labels_fields_for_the_settings_form() -> None:
    from plugins.computer_use.backend.config import ComputerUseConfig

    timeout = ComputerUseConfig.model_json_schema()["properties"]["timeout_seconds"]
    assert timeout["title"] == "单次操作超时" and timeout["unit"] == "秒"
