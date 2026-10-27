"""Context budgets reach kernel watchers as a read-only mapping and the bus as a dict."""

from __future__ import annotations

import json
from types import MappingProxyType, SimpleNamespace
from typing import Any, cast

import pytest
from shiori_sdk.context import ContextBudgetObserved
from shiori_sdk.kernel import PluginSpec
from shiori_sdk.testing.kernel import KernelHarness

from agent.core.passive_turn.reasoner import DefaultReasoner
from agent.core.runtime_support import ToolDiscoveryState
from agent.looping.ports import LLMConfig
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus


@pytest.mark.asyncio
async def test_reasoner_publishes_context_budget_to_watchers_and_the_bus() -> None:
    bus = EventBus()
    seen_bus: list[ContextBudgetObserved] = []
    bus.on(ContextBudgetObserved, lambda event: seen_bus.append(event))
    reasoner = DefaultReasoner(
        cast(Any, SimpleNamespace(provider=object(), light_provider=object())),
        LLMConfig(model="m", max_tokens=32, summary_token_limit=2000),
        ToolRegistry(),
        ToolDiscoveryState(),
        tool_search_enabled=False,
        session_manager=cast(Any, SimpleNamespace()),
        event_bus=bus,
        compaction_memory=cast(Any, SimpleNamespace()),
    )
    watched: list[ContextBudgetObserved] = []

    async def setup(ctx) -> None:
        async def watch(event: ContextBudgetObserved) -> None:
            watched.append(event)

        ctx.watch(ContextBudgetObserved, watch)

    await reasoner._kernel().start([PluginSpec("observe", setup)])
    status = {"failure_stage": "summary", "final_budget": {"schema_tokens": 0}}
    await reasoner._publish_context_budget(
        ContextBudgetObserved("role:mira", "user", status)
    )
    await KernelHarness(kernel=reasoner._kernel()).idle()

    assert isinstance(watched[0].status, MappingProxyType)
    assert watched[0].status["failure_stage"] == "summary"
    assert watched[0].status["final_budget"]["schema_tokens"] == 0
    assert seen_bus[0].status is status
    assert "summary" in json.dumps(seen_bus[0].status)
