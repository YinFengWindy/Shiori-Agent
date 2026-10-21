"""Built-in natural chat uses the role snapshot only on supported requests."""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest

from agent.context import ContextBuilder
from agent.lifecycle.phase import Phase
from agent.lifecycle.phases.prompt_render import (
    PromptRenderFrame,
    default_prompt_render_modules,
)
from agent.lifecycle.types import PromptRenderInput
from bus.event_bus import EventBus
from core.roles import RoleStore
from prompts.natural_chat import NATURAL_CHAT_PROMPT, NATURAL_CHAT_SEPARATOR


@pytest.mark.parametrize(
    "enabled,supported,minimal,selected",
    [
        (True, True, False, True),
        (False, True, False, False),
        (None, True, False, False),
        (True, False, False, False),
        (True, True, True, False),
    ],
)
async def test_natural_chat_is_host_owned_and_excludes_previews_and_minimal_requests(
    tmp_path, enabled, supported, minimal, selected
):
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="保持原有性格")
    memory = SimpleNamespace(
        read_self=lambda: "",
        read_profile=lambda: "",
        read_recent_context=lambda: "",
        get_memory_context=lambda: "",
    )
    phase = Phase(
        default_prompt_render_modules(
            EventBus(),
            ContextBuilder(tmp_path, memory=cast(Any, memory), runtime_roles=roles),
        ),
        frame_factory=PromptRenderFrame,
    )
    result = await phase.run(
        PromptRenderInput(
            session_key="role:mira",
            channel="desktop",
            chat_id="mira",
            content="hello",
            media=None,
            timestamp=datetime.now(timezone.utc),
            history=[],
            skill_names=None,
            retrieved_memory_block="",
            disabled_sections=set(),
            turn_injection_prompt="",
            session_metadata={
                "role_id": "mira",
                "role_runtime_config": {"natural_chat_enabled": enabled},
            },
            supports_reply_sequence=supported,
            minimal_request=minimal,
        )
    )
    assert (result.reply_sequence is not None) is selected
    assert (NATURAL_CHAT_PROMPT in str(result.messages[0]["content"])) is selected
    if result.reply_sequence is not None:
        assert result.reply_sequence.separator == NATURAL_CHAT_SEPARATOR
