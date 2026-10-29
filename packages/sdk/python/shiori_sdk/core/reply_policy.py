"""``REPLY_POLICY``: natural-chat prompts and strategy (P6a, D8).

The host does not own the prompt text. The ``natural_chat`` plugin provides
this key. Consumers ``get`` it on every use. ``None`` means the plugin is off:
the core still speaks, in a single message, and does not add the chat prompt.

Selection is this provider together with the role flag
``runtime_config["natural_chat_enabled"] is True``. The core keeps the
multi-message delivery protocol either way. Proactive and drift drafts do not
pass through ``PromptRendering``; they read ``draft_prompt`` from this key.
"""

from __future__ import annotations

from typing import Protocol

from shiori_sdk.kernel import Key


class ReplyPolicy(Protocol):
    """Prompt text for a selected natural-chat turn.

    ``passive_prompt`` is the system section of a passive turn. ``draft_prompt``
    is the extra system text of a proactive or drift draft, whose send tool is
    ``message_push`` rather than ``finish_reply``.
    """

    def passive_prompt(self) -> str:
        """The passive-turn system section."""
        ...

    def draft_prompt(self) -> str:
        """The proactive and drift draft system section."""
        ...


REPLY_POLICY: Key[ReplyPolicy] = Key("reply_policy")
"""Natural-chat prompts. The plugin provides this; the host never does."""
