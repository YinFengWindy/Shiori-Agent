from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.core.proactive_turn.prompt_context import (
    build_runtime_context_message,
    build_system_prompt,
)
from bootstrap.proactive import _build_role_prompt_resolver
from core.identity import IdentityChat
from core.roles import RoleStore
from conversation.service import ConversationService, LegacySessionDescriptor
from core.memory.group_environment import GroupEnvironment, GroupEnvironmentUpdate
from proactive_v2.config import ProactiveConfig
from proactive_v2.context import AgentTickContext
from proactive_v2.gateway import GatewayResult
from session.manager import SessionManager


def test_proactive_system_prompt_rejects_missing_role_identity() -> None:
    with pytest.raises(ValueError, match="role.system_prompt required"):
        build_system_prompt("  ")


RECENT_CONTEXT = (
    "## 还在继续的事\n- 周末的旅行计划\n\n" "## 最近的对话\n- user: 群里的原话\n"
)


def test_proactive_context_leaves_out_the_raw_recent_turns() -> None:
    memory = SimpleNamespace(
        bind_session_metadata=lambda metadata: None,
        read_self=lambda: "",
        read_long_term=lambda: "",
        read_recent_context=lambda: RECENT_CONTEXT,
    )

    frame = build_runtime_context_message(
        cfg=ProactiveConfig(),
        session_key="role:mira",
        tool_deps=SimpleNamespace(memory=memory, group_environment=None),
        workspace_context_fn=None,
        ctx=AgentTickContext(session_key="role:mira"),
        gateway_result=GatewayResult(),
    )

    # The raw turns span every thread; proactive reads the user context instead.
    assert "周末的旅行计划" in frame["content"]
    assert "群里的原话" not in frame["content"]


def test_proactive_system_prompt_carries_the_users_channel_identities(
    tmp_path,
) -> None:
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", role_id="mira", system_prompt="规则")
    record = store.accounts.register(
        plugin_id="qq",
        platform="qq",
        platform_account_id="101",
        config_ref="101",
        token="live",
        role_id="mira",
    ).record
    # The role prompt proactive turns are built with.
    resolve = _build_role_prompt_resolver(tmp_path, "mira", store)
    assert "你的用户在各渠道的身份" not in build_system_prompt(resolve())

    store.identities.pair(
        store.identities.create_pairing_code().code,
        record=record,
        user_id="3174898512",
        scope="platform",
        chat=IdentityChat(record.id, "qq", "3174898512"),
    )

    assert "- 渠道 qq：3174898512（整个平台通用；私聊 qq:3174898512）" in (
        build_system_prompt(resolve())
    )


def test_proactive_context_injects_recent_activity_of_external_chats(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    conversation = ConversationService(manager)
    environment = GroupEnvironment(tmp_path, manager.conversation_store)
    ctx = AgentTickContext(session_key="role:mira")
    for chat_id, age in (("g1", timedelta(hours=1)), ("g2", timedelta(days=4))):
        thread = conversation.ensure_thread_for_session(
            LegacySessionDescriptor(
                session_key=f"qq:{chat_id}",
                role_id="mira",
                channel="qq",
                chat_id=chat_id,
            )
        )
        environment.apply(
            "mira",
            GroupEnvironmentUpdate(
                thread_id=thread.id,
                label=f"群「{chat_id}」",
                recent_activity=f"{chat_id} 的最近动态",
                group_note="",
            ),
            updated_at=ctx.now_utc - age,
        )

    frame = build_runtime_context_message(
        cfg=ProactiveConfig(),
        session_key="role:mira",
        tool_deps=SimpleNamespace(memory=None, group_environment=environment),
        workspace_context_fn=None,
        ctx=ctx,
        gateway_result=GatewayResult(),
    )

    assert "g1 的最近动态" in frame["content"]
    assert "g2 的最近动态" not in frame["content"]
