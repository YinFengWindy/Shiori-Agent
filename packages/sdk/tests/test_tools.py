from __future__ import annotations

import json

import pytest

from shiori_sdk.tools import Tool


class _DummyTool(Tool):
    @property
    def name(self) -> str:
        return "dummy"

    @property
    def description(self) -> str:
        return "dummy description"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "minLength": 2},
                "count": {"type": "integer", "minimum": 1, "maximum": 3},
                "mode": {"type": "string", "enum": ["a", "b"]},
                "items": {"type": "array", "items": {"type": "number"}},
            },
            "required": ["name", "count"],
        }

    async def execute(self, **kwargs) -> str:
        return json.dumps(kwargs, ensure_ascii=False)


def test_validate_params_reports_all_schema_violations():
    tool = _DummyTool()

    errors = tool.validate_params(
        {"name": "x", "count": 5, "mode": "c", "items": ["a"]}
    )

    assert "name 最短 2 个字符" in errors
    assert "count 须 <= 3" in errors
    assert "mode 须为以下值之一" in errors[2]
    assert "[0] 应为 number 类型" in errors[3]


def test_validate_params_reports_missing_required_fields():
    assert _DummyTool().validate_params({})[:2] == [
        "缺少必填字段：name",
        "缺少必填字段：count",
    ]


def test_to_schema_exposes_tool_name():
    assert _DummyTool().to_schema()["function"]["name"] == "dummy"


def test_validate_params_rejects_non_object_schema():
    class _BadSchemaTool(_DummyTool):
        @property
        def parameters(self) -> dict:
            return {"type": "array"}

    with pytest.raises(ValueError):
        _BadSchemaTool().validate_params({})


def test_subclass_must_define_all_required_fields():
    with pytest.raises(TypeError, match="必须定义字段：description, parameters"):

        class _MissingTool(Tool):
            name = "bad"

            async def execute(self, **kwargs) -> str:
                return "ok"


def test_subclass_fields_must_not_be_empty():
    with pytest.raises(TypeError, match="字段不能为空：name, description, parameters"):

        class _EmptyTool(Tool):
            name = ""
            description = ""
            parameters = {}

            async def execute(self, **kwargs) -> str:
                return "ok"
