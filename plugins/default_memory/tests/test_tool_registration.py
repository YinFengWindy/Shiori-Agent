"""Profile-driven registration of memorize, forget, recall, and custom tools."""

from __future__ import annotations

from typing import Any, cast

import pytest
from shiori_sdk.memory.engine import MemoryToolProfile, MemoryToolSpec
from shiori_sdk.testing.tools import FakeTools

from plugins.default_memory.backend.tools.register import register_memory_meta_tools


class _MemoryEngineStub:
    def tool_profile(self) -> MemoryToolProfile:
        return MemoryToolProfile(
            recall=MemoryToolSpec(
                description="test",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                search_hint="记得",
            ),
            forget=MemoryToolSpec(
                description="test",
                parameters={
                    "type": "object",
                    "properties": {
                        "ids": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["ids"],
                },
                risk="write",
            ),
            tools=(
                MemoryToolSpec(
                    name="reinforce_memory",
                    description="test",
                    parameters={
                        "type": "object",
                        "properties": {"note": {"type": "string"}},
                        "required": [],
                    },
                    risk="write",
                    search_hint="强化",
                ),
            ),
        )


def test_register_memory_meta_tools_keeps_profile_risk_and_hints() -> None:
    tools = FakeTools()

    register_memory_meta_tools(tools, cast(Any, _MemoryEngineStub()))

    assert set(tools.tools) == {"recall_memory", "forget_memory", "reinforce_memory"}
    assert tools.options["recall_memory"]["always_on"] is True
    assert tools.options["recall_memory"]["risk"] == "read-only"
    assert tools.options["recall_memory"]["search_hint"] == "记得"
    assert tools.options["forget_memory"]["risk"] == "write"
    assert tools.options["reinforce_memory"]["search_hint"] == "强化"
    assert tools.options["reinforce_memory"]["external_allowed"] is False


def test_register_memory_meta_tools_rejects_duplicate_names() -> None:
    tools = FakeTools()
    engine = cast(Any, _MemoryEngineStub())

    register_memory_meta_tools(tools, engine)

    with pytest.raises(ValueError, match="重复注册"):
        register_memory_meta_tools(tools, engine)


def test_register_memory_meta_tools_rejects_invalid_custom_name() -> None:
    class _BadMemoryEngineStub(_MemoryEngineStub):
        def tool_profile(self) -> MemoryToolProfile:
            return MemoryToolProfile(
                tools=(
                    MemoryToolSpec(
                        name="bad-name",
                        description="test",
                        parameters={"type": "object", "properties": {}, "required": []},
                    ),
                )
            )

    tools = FakeTools()

    with pytest.raises(ValueError, match="非法"):
        register_memory_meta_tools(tools, cast(Any, _BadMemoryEngineStub()))
    assert tools.tools == {}
