from __future__ import annotations

from plugins.default_memory.backend.semantic.rule_schema import (
    build_procedure_rule_schema,
    procedure_rules_conflict,
)


def test_baseline_procedure_rules_conflict_pure_logic():
    """[PASS] procedure_rules_conflict 函数正确识别工具方向对立。"""
    # 明确对立
    new = {
        "required_tools": ["steam_mcp"],
        "forbidden_tools": ["web_search"],
        "mentioned_tools": ["steam_mcp", "web_search"],
    }
    old = {
        "required_tools": ["web_search"],
        "forbidden_tools": ["steam_mcp"],
        "mentioned_tools": ["steam_mcp", "web_search"],
    }
    assert procedure_rules_conflict(new, old) is True

    # 同方向（都要求 steam_mcp）
    new2 = {
        "required_tools": ["steam_mcp"],
        "forbidden_tools": [],
        "mentioned_tools": ["steam_mcp"],
    }
    old2 = {
        "required_tools": ["steam_mcp"],
        "forbidden_tools": [],
        "mentioned_tools": ["steam_mcp"],
    }
    assert procedure_rules_conflict(new2, old2) is False

    # 无工具交集
    new3 = {
        "required_tools": ["weather_skill"],
        "forbidden_tools": [],
        "mentioned_tools": ["weather_skill"],
    }
    old3 = {
        "required_tools": ["steam_mcp"],
        "forbidden_tools": [],
        "mentioned_tools": ["steam_mcp"],
    }
    assert procedure_rules_conflict(new3, old3) is False


def test_build_procedure_rule_schema_prefers_explicit_rule_schema():
    schema = build_procedure_rule_schema(
        "查 Steam 信息时不要直接用 web_search，必须先使用 steam MCP。",
        tool_requirement="steam_mcp",
        rule_schema={
            "required_tools": ["steam_mcp"],
            "forbidden_tools": ["web_search"],
            "mentioned_tools": ["steam", "web_search"],
        },
    )

    assert "web_search" in schema["forbidden_tools"]
    assert schema["required_tools"] == ["steam_mcp"]
    assert "steam" in schema["mentioned_tools"]


def test_build_procedure_rule_schema_fills_missing_slot_from_summary():
    schema = build_procedure_rule_schema(
        "查 Steam 信息时必须先使用 steam MCP，不能直接使用 web_search。",
        rule_schema={"required_tools": ["steam_mcp"]},
    )

    assert schema["required_tools"] == ["steam_mcp"]
    assert schema["forbidden_tools"] == ["web_search"]


def test_build_procedure_rule_schema_infers_constraints_without_explicit_schema():
    schema = build_procedure_rule_schema(
        "查 Steam 信息时不要直接用 web_search，必须先使用 steam MCP。"
    )

    assert "steam_mcp" in schema["required_tools"]
    assert "web_search" in schema["forbidden_tools"]
    assert "steam" in schema["mentioned_tools"]
