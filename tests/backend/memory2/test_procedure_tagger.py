from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.provider import LLMResponse
from memory2.procedure_tagger import ProcedureTagger, _validate

_TAGGER_PAYLOAD = (
    "```json\n"
    '{"tools":["shell","bad"],"skills":["rsshub-route-finder"],'
    '"keywords":["pacman","x"],"scope":"global"}\n'
    "```"
)


@pytest.mark.asyncio
async def test_procedure_tagger_drops_unknown_tools_skills_and_keywords():
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=LLMResponse(content=_TAGGER_PAYLOAD))
    tagger = ProcedureTagger(provider, "m", lambda: ["rsshub-route-finder"])

    tag = await tagger.tag("测试")

    request = provider.chat.await_args.kwargs
    assert request["call_purpose"] == "auxiliary"
    assert request["max_tokens"] == 128
    assert tag == {
        "tools": ["shell"],
        "skills": ["rsshub-route-finder"],
        "keywords": ["pacman"],
        "scope": "tool_triggered",
    }


@pytest.mark.asyncio
async def test_procedure_tagger_returns_none_when_provider_fails():
    provider = MagicMock()
    provider.chat = AsyncMock(side_effect=RuntimeError("x"))
    tagger = ProcedureTagger(provider, "m", lambda: ["rsshub-route-finder"])

    assert await tagger.tag("测试") is None


def test_validate_falls_back_to_tool_triggered_scope():
    validated = _validate({"scope": "bad", "keywords": ["okay"]}, {"shell"}, set())

    assert validated["scope"] == "tool_triggered"
