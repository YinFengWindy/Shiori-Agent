"""Natural chat follows the role record, not the session copy."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest

from agent.core.turn_events import TurnEvents, core_kernel
from agent.context import ContextBuilder
from agent.lifecycle.phases.prompt_render import PromptRenderPhase
from agent.lifecycle.types import PromptRenderInput, PromptRenderResult
from bus.event_bus import EventBus
from core.roles import RoleStore
from core.roles.reply_policy import (
    ReplyPolicyGetter,
    bind_turn_reply_policy,
    reset_turn_reply_policy,
)
from plugins.natural_chat.backend.prompts import NATURAL_CHAT_PROMPT
from shiori_sdk.core.conversation import PromptRendering
from shiori_sdk.kernel import Context, Kernel, PluginSpec
from shiori_sdk.prompting import PromptSectionRender


async def _render(
    tmp_path,
    kernel: Callable[[], Kernel] = core_kernel,
    *,
    enabled: bool | None = True,
    supported: bool = True,
    minimal: bool = False,
) -> PromptRenderResult:
    roles = RoleStore(tmp_path)
    roles.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="保持原有性格",
        runtime_config=(
            {"natural_chat_enabled": enabled} if enabled is not None else None
        ),
    )
    memory = SimpleNamespace(
        read_self=lambda: "",
        read_profile=lambda: "",
        read_recent_context=lambda: "",
        get_memory_context=lambda: "",
    )
    bus = EventBus()
    phase = PromptRenderPhase(
        TurnEvents(bus, kernel),
        ContextBuilder(tmp_path, memory=cast(Any, memory), runtime_roles=roles),
    )
    return await phase.run(
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
                # The copy disagrees with the role record. The record wins.
                "role_runtime_config": {"natural_chat_enabled": enabled is not True},
            },
            supports_reply_sequence=supported,
            minimal_request=minimal,
        )
    )


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
    result = await _render(
        tmp_path,
        enabled=enabled,
        supported=supported,
        minimal=minimal,
    )
    assert result.natural_chat is selected
    # Unbound, the role flag still selects the protocol, but the prompt text
    # belongs to a bound policy.
    assert NATURAL_CHAT_PROMPT not in str(result.messages[0]["content"])


async def test_prompt_rendering_handlers_choose_reply_mode_and_add_sections(tmp_path):
    async def single_reply(event: PromptRendering) -> PromptRendering:
        section = PromptSectionRender(name="probe", content="# Probe", is_static=False)
        bottom = (*event.system_sections_bottom, section)
        return replace(event, reply_mode="single", system_sections_bottom=bottom)

    async def setup(ctx: Context) -> None:
        ctx.on(PromptRendering, single_reply)

    kernel = Kernel()
    await kernel.start([PluginSpec("probe", setup)])

    result = await _render(tmp_path, lambda: kernel)

    # The role enables natural chat; the handler's choice wins.
    assert result.natural_chat is False
    system = str(result.messages[0]["content"])
    assert NATURAL_CHAT_PROMPT not in system
    assert "# Probe" in system


class _Policy:
    def passive_prompt(self) -> str:
        return NATURAL_CHAT_PROMPT

    def draft_prompt(self) -> str:
        return "draft"


async def test_bound_policy_appends_the_chat_prompt(tmp_path):
    getter = ReplyPolicyGetter()
    getter.bind(lambda: _Policy())
    token = bind_turn_reply_policy(getter)
    try:
        result = await _render(tmp_path)
    finally:
        reset_turn_reply_policy(token)

    assert result.natural_chat is True
    assert NATURAL_CHAT_PROMPT in str(result.messages[0]["content"])


async def test_bound_missing_policy_forces_a_single_reply(tmp_path):
    getter = ReplyPolicyGetter()
    getter.bind(lambda: None)
    token = bind_turn_reply_policy(getter)
    try:
        result = await _render(tmp_path)
    finally:
        reset_turn_reply_policy(token)

    assert result.natural_chat is False
    assert NATURAL_CHAT_PROMPT not in str(result.messages[0]["content"])
