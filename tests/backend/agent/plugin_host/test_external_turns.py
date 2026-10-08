"""Plugin-submitted external turns run through a real AgentLoop (#721)."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from agent.lifecycle.facade import TurnLifecycle
from agent.looping.core import AgentLoop
from agent.looping.ports import AgentLoopConfig, AgentLoopDeps, MemoryServices
from agent.plugin_host.external_turns import HostExternalTurns
from agent.provider import LLMProvider, LLMResponse, ToolCall
from agent.tools.registry import ToolRegistry
from bootstrap.wiring import wire_turn_lifecycle
from conversation.context_scope import in_desktop_view
from conversation.listening import GroupListeningControl
from conversation.service import ConversationService, desktop_thread_id
from core.accounts import AccountRegistry
from core.channel_avatars import ChannelAvatarStore
from core.channels.role_routing import RoleTurnRouter
from core.common.channel_directory import ChannelDirectory
from core.identity import IdentityChat, UserIdentityStore
from core.roles import RoleRepository, RoleRuntimeRegistry, RoleStore
from desktop_bridge.phone_requests import DesktopPhoneRequestHandler
from desktop_bridge.session_presenter import DesktopSessionPresenter
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
# Identifiable user-context content that must never reach an external turn.
SECRETS = ("DESK-SECRET", "DM-SECRET", "MEMORY-SECRET", "RECENT-SECRET")


class _Tool(Tool):
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


class _Provider(LLMProvider):
    """Records every model request; reply requests may be held by ``gates``."""

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
        return ""

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


class _Host:
    def __init__(self, tmp_path: Path) -> None:
        roles = RoleStore(tmp_path)
        roles.create_role(role_id="mira", name="Mira", system_prompt="test")
        # The desktop user is bound on QQ (902), so 902's private chat is
        # user context.
        identities = UserIdentityStore(tmp_path)
        assert identities.pair(
            identities.create_pairing_code().code,
            record=QQ_ACCOUNT,
            user_id="902",
            scope="platform",
            chat=IdentityChat(QQ_ACCOUNT.id, "qq", "902"),
        )
        self.manager = SessionManager(tmp_path)
        session = self.manager.get_or_create("role:mira")
        session.metadata["role_id"] = "mira"
        session.add_message("user", "DESK-SECRET", thread_id=desktop_thread_id("mira"))
        session.add_message(
            "assistant", "desk-reply", thread_id=desktop_thread_id("mira")
        )
        session.add_message("user", "DM-SECRET", thread_id=USER_DM)
        session.add_message("assistant", "dm-reply", thread_id=USER_DM)
        self.manager.save(session)
        self.provider = _Provider()
        tools = ToolRegistry()
        tools.register(_Tool("user_only"), always_on=True)
        tools.register(_Tool("public"), always_on=True, external_allowed=True)
        directory = ChannelDirectory()
        self.loop = AgentLoop(
            AgentLoopDeps(
                bus=MagicMock(),
                provider=cast(Any, self.provider),
                light_provider=cast(Any, self.provider),
                tools=tools,
                session_manager=self.manager,
                workspace=tmp_path,
                memory_services=MemoryServices(engine=cast(Any, _MemoryEngine())),
                role_runtime_registry=RoleRuntimeRegistry(
                    RoleRepository(roles), model_resolver=_ModelRuntime()
                ),
                channel_directory=directory,
            ),
            AgentLoopConfig(),
        )
        wire_turn_lifecycle(
            lifecycle=TurnLifecycle(self.loop._event_bus),
            active_turn_states=self.loop.active_turn_states,
        )
        self.turns = HostExternalTurns(
            RoleTurnRouter.from_workspace(
                tmp_path,
                session_manager=self.manager,
                role_store=roles,
                channel_directory=directory,
            ),
            self.loop.process_external_turn,
            role_store=roles,
            channel_directory=directory,
        )

    def desktop_turn(self, content: str) -> asyncio.Task[str]:
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
        session = SessionManager(self.manager.workspace).get_or_create("role:mira")
        return [
            (str(message["role"]), str(message["content"]))
            for message in session.messages
            if message.get("thread_id") == thread_id
        ]


def _message(text: str = "主播好", *, message_id: str = "m1") -> ExternalTurnMessage:
    return ExternalTurnMessage(
        role_id="mira",
        platform="bilibili",
        conversation_id="room-1",
        conversation_title="Mira 的直播间",
        sender_id="uid-7",
        sender_name="观众七",
        message_id=message_id,
        text=text,
    )


def _request_text(request: dict[str, Any]) -> str:
    return "\n".join(str(message.get("content")) for message in request["messages"])


def _tool_names(request: dict[str, Any]) -> set[str]:
    return {tool["function"]["name"] for tool in request.get("tools") or []}


@pytest.fixture
def host(tmp_path: Path) -> _Host:
    return _Host(tmp_path)


async def test_submitted_message_is_an_external_group_turn_in_its_own_thread(host):
    # Positive control: a desktop turn sees the user context and every tool.
    assert await host.desktop_turn("hello") == "reply-1"
    desktop_request = host.provider.requests[0]
    assert all(secret in _request_text(desktop_request) for secret in SECRETS)
    assert {"user_only", "public"} <= _tool_names(desktop_request)

    result = await host.turns.submit(_message())

    assert (result.status, result.reply) == ("replied", "reply-2")
    request = host.provider.requests[1]
    text = _request_text(request)
    assert not any(secret in text for secret in SECRETS)
    # The sender is a group member, never the bound user.
    assert "群友「观众七」（ID uid-7）" in text
    assert "public" in _tool_names(request)
    assert "user_only" not in _tool_names(request)
    assert host.stored(ROOM) == [("user", "主播好"), ("assistant", "reply-2")]
    assert not in_desktop_view("mira", ROOM)
    # The phone lists the conversation by its title, with no channel account.
    workspace = host.manager.workspace
    conversation = ConversationService(SessionManager(workspace))
    phone = DesktopPhoneRequestHandler(
        conversations=conversation,
        accounts=AccountRegistry({"mira"}.__contains__),
        identities=UserIdentityStore(workspace),
        messages=DesktopSessionPresenter(conversation),
        avatars=ChannelAvatarStore(workspace),
        listening=GroupListeningControl(conversation, lambda _channel: False),
    )
    listed = await phone.handle("phone.conversations.list", {"role_id": "mira"})
    assert listed is not None
    row = next(row for row in listed["conversations"] if row["thread_id"] == ROOM)
    assert (row["display_name"], row["channel"], row["chat_type"]) == (
        "Mira 的直播间",
        "bilibili",
        "group",
    )
    assert row["account_id"] is None
    assert row["is_user_chat"] is False


async def test_replayed_message_id_runs_nothing(host):
    assert (await host.turns.submit(_message())).status == "replied"

    result = await host.turns.submit(_message("again"))

    assert result.status == "duplicate"
    assert len(host.provider.requests) == 1
    assert host.stored(ROOM) == [("user", "主播好"), ("assistant", "reply-1")]


async def test_busy_role_returns_busy_at_once_and_stores_nothing(host):
    gate = asyncio.Event()
    host.provider.gates.append(gate)
    desktop = host.desktop_turn("hello")
    await host.provider.started.wait()

    result = await asyncio.wait_for(host.turns.submit(_message()), timeout=1)

    assert result.status == "busy"
    gate.set()
    assert await desktop == "reply-1"
    assert host.stored(ROOM) == []
    assert len(host.provider.requests) == 1


async def test_desktop_interrupt_never_reaches_an_external_turn(host):
    # The external turn calls a tool (reporting progress), then waits.
    host.provider.tool_steps = 1
    step, finish = asyncio.Event(), asyncio.Event()
    host.provider.gates.extend([step, finish])
    external = asyncio.create_task(host.turns.submit(_message()))
    await host.provider.started.wait()
    # A desktop message waits for the role while the external turn runs.
    desktop = host.desktop_turn("hello")
    await asyncio.sleep(0)
    host.provider.started.clear()
    step.set()
    await host.provider.started.wait()

    interrupted = host.loop.request_interrupt("role:mira", command="/cancel")

    # Only the waiting desktop turn is interrupted, and its snapshot holds no
    # progress of the external turn.
    assert interrupted.status == "interrupted"
    assert interrupted.state is not None
    assert interrupted.state.original_user_message == "hello"
    assert interrupted.state.partial_reply == ""
    assert interrupted.state.tools_used == []
    with pytest.raises(asyncio.CancelledError):
        await desktop
    assert host.loop.request_interrupt("role:mira").status == "idle"
    finish.set()
    assert (await external).reply == "reply-2"
    assert host.stored(ROOM)[0] == ("user", "主播好")
    assert host.stored(ROOM)[-1] == ("assistant", "reply-2")


async def test_cancelling_an_external_turn_leaves_the_waiting_desktop_turn(host):
    host.provider.gates.append(asyncio.Event())
    external = asyncio.create_task(host.turns.submit(_message()))
    await host.provider.started.wait()
    desktop = host.desktop_turn("hello")
    await asyncio.sleep(0)

    external.cancel()

    with pytest.raises(asyncio.CancelledError):
        await external
    assert await desktop == "reply-2"
    assert host.stored(desktop_thread_id("mira"))[-2:] == [
        ("user", "hello"),
        ("assistant", "reply-2"),
    ]


@pytest.mark.parametrize(
    ("change", "error"),
    [({"role_id": "nobody"}, "角色不存在"), ({"platform": "desktop"}, "宿主渠道名")],
)
async def test_unknown_role_or_host_transport_is_rejected(host, change, error):
    message = _message()
    fields = {**message.__dict__, **change}

    with pytest.raises(ValueError, match=error):
        await host.turns.submit(ExternalTurnMessage(**fields))
    assert host.provider.requests == []
