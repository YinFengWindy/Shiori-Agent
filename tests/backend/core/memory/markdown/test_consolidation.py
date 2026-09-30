"""Group extraction captures both saved fields before awaiting the model."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.provider import LLMProvider, LLMResponse
from conversation.store import ConversationStore
from core.identity import BoundUserSenders
from core.memory.external_writes import edit_group_environment
from core.memory.group_environment import GroupEnvironment
from core.memory.markdown import (
    MarkdownMemoryStore,
    _MarkdownConsolidationWorker as ConsolidationWorker,
)
from core.memory.markdown.contracts import ExternalLayerUpdates
from core.memory.markdown.external_segment import ExternalThread
from core.memory.member_profiles import MemberProfiles


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["recent_activity", "group_note"])
async def test_extraction_snapshots_the_group_even_when_the_model_updates_one_field(
    tmp_path: Path, field: str
) -> None:
    environment = GroupEnvironment(
        tmp_path, ConversationStore(tmp_path / "sessions.db")
    )
    thread_id = "thread:mira:qq:g"
    before = environment.read("mira", thread_id)

    async def reply(**_kwargs: object) -> LLMResponse:
        _ = edit_group_environment(
            environment,
            "mira",
            thread_id,
            summary="用户修订",
            label="群",
            updated_at=datetime.now().astimezone(),
        )
        return LLMResponse(content=json.dumps({field: "模型内容"}))

    provider = MagicMock(spec=LLMProvider)
    provider.chat = AsyncMock(side_effect=reply)
    worker = ConsolidationWorker(
        profile_maint=MarkdownMemoryStore(tmp_path),
        provider=provider,
        model="test",
        keep_count=0,
    )
    result = await worker.extract_external_layers(
        [
            ExternalThread(
                thread_id,
                "群",
                [{"role": "user", "content": "群消息"}],
                BoundUserSenders((), ()),
            )
        ],
        group_environment=environment,
        member_profiles=MemberProfiles(tmp_path),
        role_id="mira",
        nsfw_memory_enabled=False,
    )

    assert isinstance(result, ExternalLayerUpdates)
    assert len(result.group_environment) == 1
    assert result.snapshot.group_environments == {thread_id: before}
    assert environment.read("mira", thread_id).recent_activity == "用户修订"
