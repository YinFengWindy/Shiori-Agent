"""``CONVERSATION`` delivers for the role that owns the reply's session."""

from __future__ import annotations

from functools import partial

from agent.initiated_delivery import HostConversation, orchestrator_for
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from bootstrap.tools import _validate_role_target
from bus.event_bus import EventBus
from core.roles import RoleRepository, RoleStore
from core.roles.affection_access import AffectionGetter
from core.roles.reply_policy import ReplyPolicyGetter
from session.manager import SessionManager
from shiori_sdk.core.conversation import InitiatedDelivery, InitiatedReply


async def test_reply_to_another_roles_desktop_is_refused(tmp_path) -> None:
    roles = RoleStore(tmp_path)
    for role_id in ("mira", "other"):
        roles.create_role(
            role_id=role_id,
            name=role_id,
            system_prompt="规矩",
            runtime_config={"mood_catalog": ["想你"]},
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
    try:
        delivery = await conversation.deliver_initiated_reply(
            InitiatedReply(
                session_key="role:mira",
                content="给别人的桌面",
                source="drift",
                channel="desktop",
                chat_id="role:other",
                mood="想你",
                thought="我想你",
                expected_mood_updated_at="",
                moods=("想你",),
            )
        )
    finally:
        await bus.aclose()
    assert delivery == InitiatedDelivery(message_ids=(), complete=False)
    assert sent == []
    assert manager._store.fetch_session_messages("role:mira") == []
