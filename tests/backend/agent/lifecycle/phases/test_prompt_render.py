"""Natural chat follows the role snapshot, or the PromptRendering reply mode."""

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
from prompts.natural_chat import NATURAL_CHAT_PROMPT
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
    roles.create_role(role_id="mira", name="Mira", system_prompt="保持原有性格")
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
                "role_runtime_config": {"natural_chat_enabled": enabled},
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
    assert (NATURAL_CHAT_PROMPT in str(result.messages[0]["content"])) is selected


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
