"""Natural-chat prompts and selection. The core still splits and delivers."""

from __future__ import annotations

from shiori_sdk.core.reply_policy import REPLY_POLICY, ReplyPolicy
from shiori_sdk.runtime import PluginRuntimeContext

from .prompts import NATURAL_CHAT_DRAFT_PROMPT, NATURAL_CHAT_PROMPT


class NaturalChatPolicy:
    """Prompt text for a selected natural-chat turn."""

    def passive_prompt(self) -> str:
        """Appended after ``PromptRendering`` when the reply is a sequence."""
        return NATURAL_CHAT_PROMPT

    def draft_prompt(self) -> str:
        """Appended to a proactive or drift draft that skips ``PromptRendering``."""
        return NATURAL_CHAT_DRAFT_PROMPT


async def setup(ctx: PluginRuntimeContext) -> None:
    """Provides ``REPLY_POLICY``. A disabled plugin leaves the getter empty."""
    policy: ReplyPolicy = NaturalChatPolicy()
    ctx.provide(REPLY_POLICY, policy)
