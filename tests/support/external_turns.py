"""A real AgentLoop for plugin-submitted external turns (#721).

Only the model provider, the role model resolver and the memory engine are
stand-ins; sessions, roles, routing, prompts and the turn pipeline are the
host's own. The desktop user is bound on QQ (902), and the role session holds
identifiable user-context content that an external turn must never see.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from agent.lifecycle.facade import TurnLifecycle
from agent.looping.core import AgentLoop
from agent.looping.ports import AgentLoopConfig, AgentLoopDeps, MemoryServices
from agent.plugin_host.external_turns import HostExternalTurns
from agent.provider import LLMProvider, LLMResponse, ToolCall
from agent.tools.registry import ToolRegistry
from bootstrap.wiring import wire_turn_lifecycle
from conversation.service import desktop_thread_id
from core.channels.role_routing import RoleTurnRouter
from core.common.channel_directory import ChannelDirectory
from core.identity import IdentityChat, UserIdentityStore
from core.memory.group_environment import GroupEnvironment
from core.memory.markdown_schema import (
    SELF_PERSONA_SECTION,
    SELF_RELATIONSHIP_SECTION,
    SELF_UNDERSTANDING_SECTION,
)
from core.roles import RoleRepository, RoleRuntimeRegistry, RoleStore
from session.manager import SessionManager
from shiori_sdk.accounts.models import AccountRecord
from shiori_sdk.channels.threads import network_thread_id
from shiori_sdk.external_turns import ExternalTurnMessage
from shiori_sdk.memory.engine import MemoryQueryResult
from shiori_sdk.tools import Tool

QQ_ACCOUNT = AccountRecord(
    id="qq:101",
    plugin_id="qq",
    platform="qq",
    platform_account_id="101",
    config_ref="101",
    role_id="mira",
)
USER_DM = network_thread_id("mira", "qq", "902")
ROOM = network_thread_id("mira", "bilibili", "room-1")
ROOM_TITLE = "Mira 的直播间"
# Identifiable user-context content that must never reach an external turn.
SECRETS = (
    "DESK-SECRET",
    "DM-SECRET",
    "MEMORY-SECRET",
    "RECENT-SECRET",
    "SELF-PRIVATE-SECRET",
)
# SELF.md: the two sections external turns get, and one they never do.
SELF_TEXT = (
    f"{SELF_PERSONA_SECTION}\n\nSELF-PERSONA\n\n"
    f"{SELF_RELATIONSHIP_SECTION}\n\nSELF-RELATIONSHIP\n\n"
    f"{SELF_UNDERSTANDING_SECTION}\n\nSELF-PRIVATE-SECRET\n"
)


class NamedTool(Tool):
    """A tool that does nothing, named ``name``."""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._name

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs) -> str:
        return "ok"


class RecordingProvider(LLMProvider):
    """Records every reply request; requests may be held by ``gates``."""

    def __init__(self) -> None:
        super().__init__(
            api_key="test", model_context_window=128000, default_max_tokens=8192
        )
        self.requests: list[dict[str, Any]] = []
        # Reply requests (in order) wait on these events before answering.
        self.gates: list[asyncio.Event] = []
        # The first reply requests (in order) call the ``public`` tool instead.
        self.tool_steps = 0
        self.started = asyncio.Event()

    async def chat(self, **kwargs):  # type: ignore[override]
        reply = f"reply-{len(self.requests)}"
        if kwargs.get("response_format"):
            return LLMResponse(
                content=f'{{"content":"{reply}","mood":"平静","thought":"嗯。"}}',
                tool_calls=[],
            )
        self.requests.append(kwargs)
        reply = f"reply-{len(self.requests)}"
        self.started.set()
        if self.gates:
            await self.gates.pop(0).wait()
        if self.tool_steps:
            self.tool_steps -= 1
            return LLMResponse(
                content="external progress", tool_calls=[ToolCall("t1", "public", {})]
            )
        return LLMResponse(content=reply, tool_calls=[])


class _ModelRuntime:
    @contextmanager
    def activate(self, role_id: str, purpose: str):
        yield SimpleNamespace(model="role-model")


class _MemoryEngine:
    """User-layer memory with identifiable text."""

    def read_self(self) -> str:
        return SELF_TEXT

    def read_recent_context(self) -> str:
        return "RECENT-SECRET"

    def get_memory_context(self) -> str:
        return "MEMORY-SECRET"

    def read_profile(self) -> str:
        return "MEMORY-SECRET"

    def has_long_term_memory(self) -> bool:
        return True

    async def query(self, request) -> MemoryQueryResult:
        return MemoryQueryResult(text_block="", records=[], raw={})

    async def refresh_recent_turns(self, request) -> None:
        return None

    async def consolidate(self, request) -> None:
        return None


def room_message(
    text: str = "主播好", *, message_id: str = "m1"
) -> ExternalTurnMessage:
    """A viewer message in the live room ``ROOM``."""
    return ExternalTurnMessage(
        role_id="mira",
        platform="bilibili",
        conversation_id="room-1",
        conversation_title=ROOM_TITLE,
        sender_id="uid-7",
        sender_name="观众七",
        message_id=message_id,
        text=text,
    )


def request_text(request: dict[str, Any]) -> str:
    """Everything one model request showed the model."""
    return "\n".join(str(message.get("content")) for message in request["messages"])


def tool_names(request: dict[str, Any]) -> set[str]:
    """The tools one model request offered."""
    return {tool["function"]["name"] for tool in request.get("tools") or []}


class ExternalTurnHost:
    """Role ``mira`` with a desktop user, a real loop and the host capability."""

    def __init__(self, workspace: Path) -> None:
        self.roles = RoleStore(workspace)
        self.roles.create_role(role_id="mira", name="Mira", system_prompt="test")
        identities = UserIdentityStore(workspace)
        assert identities.pair(
            identities.create_pairing_code().code,
            record=QQ_ACCOUNT,
            user_id="902",
            scope="platform",
            chat=IdentityChat(QQ_ACCOUNT.id, "qq", "902"),
        )
        self.manager = SessionManager(workspace)
        session = self.manager.get_or_create("role:mira")
        session.metadata["role_id"] = "mira"
        desktop = desktop_thread_id("mira")
        session.add_message("user", "DESK-SECRET", thread_id=desktop)
        session.add_message("assistant", "desk-reply", thread_id=desktop)
        session.add_message("user", "DM-SECRET", thread_id=USER_DM)
        session.add_message("assistant", "dm-reply", thread_id=USER_DM)
        self.manager.save(session)
        self.provider = RecordingProvider()
        tools = ToolRegistry()
        tools.register(NamedTool("user_only"), always_on=True)
        tools.register(NamedTool("public"), always_on=True, external_allowed=True)
        directory = ChannelDirectory()
        self.loop = AgentLoop(
            AgentLoopDeps(
                bus=MagicMock(),
                provider=cast(Any, self.provider),
                light_provider=cast(Any, self.provider),
                tools=tools,
                session_manager=self.manager,
                workspace=workspace,
                memory_services=MemoryServices(engine=cast(Any, _MemoryEngine())),
                role_runtime_registry=RoleRuntimeRegistry(
                    RoleRepository(self.roles), model_resolver=_ModelRuntime()
                ),
                channel_directory=directory,
            ),
            AgentLoopConfig(),
        )
        self.group_environment = GroupEnvironment(
            workspace, self.manager.conversation_store
        )
        self.loop.context.set_group_environment(self.group_environment)
        wire_turn_lifecycle(
            lifecycle=TurnLifecycle(self.loop._event_bus),
            active_turn_states=self.loop.active_turn_states,
        )
        self.router = RoleTurnRouter.from_workspace(
            workspace,
            session_manager=self.manager,
            role_store=self.roles,
            channel_directory=directory,
        )
        self.turns = HostExternalTurns(
            self.router, self.loop.process_external_turn, channel_directory=directory
        )

    def desktop_turn(self, content: str) -> asyncio.Task[str]:
        """Starts a desktop chat turn of ``mira``."""
        return asyncio.create_task(
            self.loop.process_direct(
                content,
                channel="desktop",
                chat_id="role:mira",
                metadata={
                    "role_id": "mira",
                    "thread_id": desktop_thread_id("mira"),
                    "transport_channel": "desktop",
                    "transport_chat_id": "role:mira",
                },
            )
        )

    def stored(self, thread_id: str) -> list[tuple[str, str]]:
        """(role, content) of the stored messages of ``thread_id``, as reloaded."""
        session = SessionManager(self.manager.workspace).get_or_create("role:mira")
        return [
            (str(message["role"]), str(message["content"]))
            for message in session.messages
            if message.get("thread_id") == thread_id
        ]
