"""``CONVERSATION`` delivers for the role that owns the reply's session."""

from __future__ import annotations

from functools import partial

import pytest

from agent.initiated_delivery import HostConversation, orchestrator_for
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from bootstrap.tools import _validate_role_target
from bus.event_bus import EventBus
from core.roles import RoleRepository, RoleStore
from core.roles.affection_access import AffectionGetter
from core.roles.reply_policy import ReplyPolicyGetter
from session.manager import SessionManager
from shiori_sdk.core.conversation import InitiatedReply, InitiatedToolFact


def _conversation(tmp_path):
    roles = RoleStore(tmp_path)
    for role_id in ("mira", "other"):
        roles.create_role(
            role_id=role_id,
            name=role_id,
            system_prompt="规矩",
            runtime_config={"mood_catalog": ["想你"], "natural_chat_enabled": True},
        )
    repository = RoleRepository(roles)
    # The runtime's own role target check (``build_core_runtime``).
    push = MessagePushTool(
        role_target_validator=lambda role_id, channel, chat_id: _validate_role_target(
            repository, role_id=role_id, channel=channel, chat_id=chat_id
        )
    )
    sent: list[str] = []

    async def desktop(chat_id, message, metadata):
        sent.append(chat_id)

    push.register_channel("desktop", text_with_metadata=desktop)
    manager = SessionManager(tmp_path)
    bus = EventBus()
    affection = AffectionGetter()
    affection.bind(lambda: None)
    reply_policy = ReplyPolicyGetter()
    reply_policy.bind(lambda: None)
    conversation = HostConversation(
        partial(
            orchestrator_for,
            session_manager=manager,
            presence=None,
            push_tool=push,
            event_bus=bus,
            tools=ToolRegistry(),
            role_store=roles,
        ),
        role_store=roles,
        session_manager=manager,
        affection=affection,
        reply_policy=reply_policy,
    )
    return conversation, manager, bus, sent


def _reply(**overrides) -> InitiatedReply:
    fields = {
        "session_key": "role:mira",
        "content": "给别人的桌面",
        "source": "drift",
        "channel": "desktop",
        "chat_id": "role:mira",
        "mood": "想你",
        "thought": "我想你",
        "expected_mood_updated_at": "",
        "moods": ("想你",),
    }
    fields.update(overrides)
    return InitiatedReply(**fields)


_FACT = InitiatedToolFact(
    call_id="c1", name="weather", arguments={"city": "杭州"}, result="有雨"
)


@pytest.mark.parametrize(
    "reply",
    [
        pytest.param(_reply(chat_id="role:other"), id="single"),
        pytest.param(
            _reply(
                chat_id="role:other",
                content="先说\n\n再说",
                messages=("先说", "再说"),
                tool_facts=(_FACT,),
            ),
            id="sequence-with-tool-facts",
        ),
    ],
)
async def test_reply_to_another_roles_desktop_writes_nothing(
    tmp_path, reply: InitiatedReply
) -> None:
    conversation, manager, bus, sent = _conversation(tmp_path)
    try:
        with pytest.raises(ValueError, match="桌面目标不属于角色"):
            await conversation.deliver_initiated_reply(reply)
    finally:
        await bus.aclose()
    assert sent == []
    assert manager._store.fetch_session_messages("role:mira") == []


async def test_padded_session_key_is_not_a_role_session(tmp_path) -> None:
    conversation, manager, bus, sent = _conversation(tmp_path)
    try:
        with pytest.raises(ValueError, match="只接受角色会话"):
            await conversation.deliver_initiated_reply(_reply(session_key="role:mira "))
    finally:
        await bus.aclose()
    assert sent == []
    assert manager._store.fetch_session_messages("role:mira ") == []
