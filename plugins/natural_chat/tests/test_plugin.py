"""``natural_chat`` fills the reply-policy socket the core selects with."""

from __future__ import annotations

from shiori_sdk.core.reply_policy import REPLY_POLICY
from shiori_sdk.testing.context import FakePluginContext

from plugins.natural_chat.backend.plugin import setup


async def test_setup_provides_a_policy_with_separate_passive_and_draft_prompts(
    sdk_context: FakePluginContext,
) -> None:
    await setup(sdk_context)

    policy = sdk_context.kernel.get(REPLY_POLICY)
    assert policy is not None
    # Passive turns end with finish_reply, drafts with message_push.
    assert policy.passive_prompt() and policy.draft_prompt()
    assert policy.passive_prompt() != policy.draft_prompt()
