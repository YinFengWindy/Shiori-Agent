from types import SimpleNamespace

import pytest

from proactive_v2.config import ProactiveConfig
from proactive_v2.judge import Judge


class _RecordingProvider:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def chat(self, **kwargs):
        self.messages = list(kwargs["messages"])
        return SimpleNamespace(
            content=('{"information_gap":4,"relevance":4,"expected_impact":4}')
        )


@pytest.mark.asyncio
async def test_judge_uses_complete_migrated_scoring_contract() -> None:
    provider = _RecordingProvider()
    judge = Judge(
        provider=provider,
        model="test-model",
        max_tokens=256,
        format_recent=lambda _recent: "最近聊过电竞",
        cfg=ProactiveConfig(),
    )

    await judge.judge_message(
        message="FURIA 刚结束一场比赛",
        recent=[],
        recent_proactive_text="无",
        preference_block="关注 HLTV Top 15 队伍",
        age_hours=0,
        sent_24h=0,
        interrupt_factor=1,
    )

    prompt = str(provider.messages[1]["content"])
    assert "1：明显不成立/几乎没有价值" in prompt
    assert "5：很强，强价值且很贴合" in prompt
    assert "CS2/电竞相关消息" in prompt
    assert "HLTV Top 15" in prompt
