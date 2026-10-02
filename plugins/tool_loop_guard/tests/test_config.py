from plugins.tool_loop_guard.backend.config import ToolLoopGuardConfig


def test_default_floor_and_settings_labels():
    assert ToolLoopGuardConfig().repeat_limit == 3
    assert ToolLoopGuardConfig(repeat_limit=2).repeat_limit == 2
    limit = ToolLoopGuardConfig.model_json_schema()["properties"]["repeat_limit"]
    assert limit["title"] == "重复调用上限" and limit["unit"] == "次"
