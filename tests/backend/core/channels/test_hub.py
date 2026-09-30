from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from bus.events import InboundMessage, OutboundMessage
from core.channels import ChannelHub
from core.accounts.models import AccountResponseRules
from core.common.channel_directory import ChannelDirectory
from core.roles import RoleAggregateService, RoleStore
from session.manager import SessionManager


def test_channel_hub_routes_owned_inbound_to_role_session(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    _ = service.create_role(
        role_id="mira",
        name="Mira",
        description="bound role",
        system_prompt="you are mira",
    )
    account_id = _live_account(service, "telegram")
    hub = ChannelHub(service, channel_directory=_directory_with_private_telegram())

    routed = hub.route_inbound(
        InboundMessage(
            channel="telegram",
            sender="u1",
            chat_id="123",
            content="hello",
            timestamp=datetime.now(),
            metadata={"account_id": account_id},
        )
    )

    assert routed.session_key == "role:mira"
    assert routed.metadata["thread_id"] == "thread:mira:telegram:123"
    assert routed.metadata["sender_id"] == "u1"
    assert routed.metadata["chat_type"] == "private"
    role_session = session_manager.get_or_create("role:mira")
    assert role_session.metadata["role_name"] == "Mira"
    assert (
        not {
            "thread_id",
            "context_channel",
            "context_chat_id",
            "transport_channel",
            "transport_chat_id",
        }
        & role_session.metadata.keys()
    )
    assert session_manager._store.get_session_meta("thread:mira:telegram:123") is None


def _directory_with_private_telegram() -> ChannelDirectory:
    class _Telegram:
        default_chat_type = "private"

    directory = ChannelDirectory()
    directory.bind({"telegram": _Telegram()}.get)
    return directory


def _live_account(
    service: RoleAggregateService,
    platform: str,
    rules: AccountResponseRules | None = None,
) -> str:
    accounts = service.repository.store.accounts
    account = accounts.register(
        plugin_id=platform,
        platform=platform,
        platform_account_id="self",
        config_ref="self",
        token="live",
        role_id="mira",
        response_rules=rules,
    )
    accounts.report(account.record.id, "live", connection="online")
    return account.record.id


def test_account_inbound_uses_owner_and_rules(
    tmp_path: Path,
) -> None:
    sessions = SessionManager(tmp_path)
    store = RoleStore(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path, role_store=store, session_manager=sessions
    )
    service.create_role(role_id="mira", name="Mira", system_prompt="mira")
    service.create_role(role_id="other", name="Other", system_prompt="other")
    accounts = store.accounts
    accounts.set_rules_handler("qq", lambda *_: None)
    account = accounts.register(
        plugin_id="qq",
        platform="qq",
        platform_account_id="100",
        config_ref="one",
        token="live",
        role_id="mira",
    )
    account_id = account.record.id
    accounts.report(account_id, "live", connection="online")
    hub = ChannelHub(service)
    message = InboundMessage(
        channel="qq",
        sender="user",
        chat_id="gqq:42",
        content="hello",
        metadata={"account_id": account_id, "chat_type": "group", "mentioned": True},
    )

    with pytest.raises(PermissionError):
        hub.route_inbound(
            InboundMessage(
                channel="qq",
                sender="user",
                chat_id="gqq:42",
                content="hello",
                metadata={"account_id": ""},
            )
        )

    # A group message only reaches the role when it @s or replies to the role.
    def group_message(**metadata: object) -> InboundMessage:
        return InboundMessage(
            channel=message.channel,
            sender=message.sender,
            chat_id=message.chat_id,
            content=message.content,
            metadata={**message.metadata, "mentioned": False, **metadata},
        )

    assert hub.route_account_inbound(group_message()) is None
    assert hub.route_account_inbound(group_message(reply_to_sender_id="555")) is None
    assert hub.route_account_inbound(group_message(reply_to_sender_id="100"))
    routed = hub.route_account_inbound(message)
    assert routed is not None
    assert routed.session_key == "role:mira"
    assert routed.metadata["source"] == "role_account"
    assert hub.resolve_account_runtime_session_key(account_id) == "role:mira"
    accounts.set_response_rules(account_id, AccountResponseRules(group_enabled=False))
    assert hub.route_account_inbound(message) is None
    # The account-wide blacklist gates every group too.
    accounts.set_response_rules(
        account_id, AccountResponseRules(blocked_sender_ids=("user",))
    )
    assert hub.route_account_inbound(message) is None
    # An unloaded plugin's account no longer routes anything.
    accounts.release(account_id, "live")
    assert hub.route_account_inbound(message) is None


def test_account_inbound_accepts_telegram_instance_channel_name(tmp_path: Path) -> None:
    sessions = SessionManager(tmp_path)
    store = RoleStore(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path, role_store=store, session_manager=sessions
    )
    service.create_role(role_id="mira", name="Mira", system_prompt="mira")
    accounts = store.accounts
    account = accounts.register(
        plugin_id="telegram",
        platform="telegram",
        platform_account_id="123",
        config_ref="second",
        token="live",
        role_id="mira",
    )
    accounts.report(account.record.id, "live", connection="online")

    routed = ChannelHub(service).route_account_inbound(
        InboundMessage(
            channel="telegram_second",
            sender="42",
            chat_id="42",
            content="hello",
            metadata={"account_id": account.record.id, "chat_type": "private"},
        )
    )
    assert routed is not None
    assert routed.session_key == "role:mira"


def test_channel_hub_chat_type_default_comes_from_the_channel(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    _ = service.create_role(role_id="mira", name="Mira", system_prompt="mira")
    account_ids = {
        channel: _live_account(service, channel) for channel in ("telegram", "qqbot")
    }
    hub = ChannelHub(service, channel_directory=_directory_with_private_telegram())

    def _route(channel: str, chat_id: str, sender: str, **metadata: str):
        return hub.route_inbound(
            InboundMessage(
                channel=channel,
                sender=sender,
                chat_id=chat_id,
                content="hello",
                metadata={
                    "account_id": account_ids[channel],
                    "mentioned": True,
                    **metadata,
                },
            )
        ).metadata["chat_type"]

    assert _route("telegram", "123", "u1") == "private"
    assert _route("telegram", "123", "u1", chat_type="group") == "group"
    assert _route("qqbot", "c2c:u2", "u2") == "unknown"
    assert (
        ChannelHub(service)
        .route_inbound(
            InboundMessage(
                channel="telegram",
                sender="u1",
                chat_id="123",
                content="hi",
                metadata={"account_id": account_ids["telegram"]},
            )
        )
        .metadata["chat_type"]
        == "unknown"
    )


def test_channel_hub_marks_delivery_by_role_session(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    service.create_role(
        role_id="mira",
        name="Mira",
        description="bound role",
        system_prompt="you are mira",
    ).role
    account_id = _live_account(service, "telegram")
    routed = ChannelHub(service).route_inbound(
        InboundMessage(
            channel="telegram",
            sender="u1",
            chat_id="123",
            content="hello",
            metadata={"account_id": account_id},
        )
    )
    session = session_manager.get_or_create(routed.session_key)
    session.add_message(
        "assistant",
        "reply",
        thread_id="thread:mira:telegram:123",
    )
    session_manager.save(session)
    committed_message_id = str(session.messages[-1]["id"])
    hub = ChannelHub(service)

    updated = hub.mark_delivery(
        OutboundMessage(
            channel="telegram",
            chat_id="123",
            content="reply",
            metadata={
                "role_id": "mira",
                "session_key_override": "role:mira",
                "thread_id": str(routed.metadata["thread_id"]),
            },
            committed_message_id=committed_message_id,
        ),
        default_channel="telegram",
        delivery_status="sent",
        external_message_id="tg-1",
    )

    assert updated is not None
    assert updated["id"] == committed_message_id
    assert updated["delivery_status"] == "sent"
    assert updated["external_message_id"] == "tg-1"


def test_channel_hub_skips_delivery_mark_when_outbound_has_no_committed_message(
    tmp_path: Path,
) -> None:
    """Regresses the #305 incident: a fallback outbound message built from reused

    inbound metadata (no reference to any persisted row, e.g. the "处理消息时出错，
    请稍后再试。" turn-failure notice) must never fall back to guessing "the
    thread's latest assistant message" and must leave that unrelated, already
    delivered message's bookkeeping untouched.
    """
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    service.create_role(
        role_id="mira",
        name="Mira",
        description="bound role",
        system_prompt="you are mira",
    ).role
    account_id = _live_account(service, "telegram")
    routed = ChannelHub(service).route_inbound(
        InboundMessage(
            channel="telegram",
            sender="u1",
            chat_id="123",
            content="hello",
            metadata={"account_id": account_id},
        )
    )
    thread_id = str(routed.metadata["thread_id"])
    session = session_manager.get_or_create(routed.session_key)
    # An unrelated, already-delivered proactive push sitting as the thread's
    # latest assistant message when the failed turn's fallback fires later.
    session.add_message("assistant", "unrelated proactive push", thread_id=thread_id)
    session_manager.save(session)
    unrelated_message_id = str(session.messages[-1]["id"])
    hub = ChannelHub(service)
    baseline = hub.mark_delivery(
        OutboundMessage(
            channel="telegram",
            chat_id="123",
            content="unrelated proactive push",
            metadata={
                "role_id": "mira",
                "session_key_override": "role:mira",
                "thread_id": thread_id,
            },
            committed_message_id=unrelated_message_id,
        ),
        default_channel="telegram",
        delivery_status="sent",
        external_message_id="tg-earlier",
    )
    assert baseline is not None
    assert baseline["delivery_status"] == "sent"
    assert baseline["external_message_id"] == "tg-earlier"

    # A later turn fails; its control-path fallback reuses the inbound
    # message's metadata (role_id/thread_id/session_key_override) but was
    # never persisted, so it carries no committed_message_id.
    fallback = OutboundMessage(
        channel="telegram",
        chat_id="123",
        content="处理消息时出错，请稍后再试。",
        metadata={
            "role_id": "mira",
            "session_key_override": "role:mira",
            "thread_id": thread_id,
        },
    )

    result = hub.mark_delivery(
        fallback,
        default_channel="telegram",
        delivery_status="sent",
        external_message_id="tg-inbound-id",
    )

    assert result is None
    after = session_manager._store.get_message(unrelated_message_id)
    assert after is not None
    assert after["delivery_status"] == "sent"
    assert after["external_message_id"] == "tg-earlier"


def test_channel_hub_skips_delivery_mark_without_running_thread_validation(
    tmp_path: Path,
) -> None:
    """The missing-committed-id early return must run before any thread checks.

    A channel outbound's ``finally`` block calls ``mark_delivery`` unguarded by
    a ``try``, so a ``ValueError`` raised from thread validation would escape
    straight out of the send path. A fallback message with no
    ``committed_message_id`` has nothing to mark regardless of whether its
    metadata even carries a usable thread_id, so it must return ``None``
    quietly instead of ever reaching those validations.
    """
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    role = service.create_role(
        role_id="mira",
        name="Mira",
        description="bound role",
        system_prompt="you are mira",
    ).role
    hub = ChannelHub(service)

    # No committed_message_id and no thread_id metadata at all: a full-blown
    # thread validation would raise ValueError("出站消息缺少 thread_id"), but
    # since there is nothing to mark, mark_delivery must short-circuit first.
    result = hub.mark_delivery(
        OutboundMessage(
            channel="telegram",
            chat_id="123",
            content="处理消息时出错，请稍后再试。",
            metadata={"role_id": role.id},
        ),
        default_channel="telegram",
        delivery_status="sent",
    )

    assert result is None


def test_channel_hub_marks_archived_external_messages_as_duplicates(
    tmp_path: Path,
) -> None:
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    service.create_role(
        role_id="mira",
        name="Mira",
        description="bound role",
        system_prompt="you are mira",
    ).role
    account_id = _live_account(service, "telegram")
    hub = ChannelHub(service)
    first = hub.route_inbound(
        InboundMessage(
            channel="telegram",
            sender="u1",
            chat_id="123",
            content="hello",
            metadata={"account_id": account_id, "external_message_id": "message-1"},
        )
    )
    session = session_manager.get_or_create(first.session_key)
    session.add_message(
        "user",
        "hello",
        thread_id=str(first.metadata["thread_id"]),
        external_message_id="message-1",
    )
    session_manager.save(session)

    duplicate = hub.route_inbound(
        InboundMessage(
            channel="telegram",
            sender="u1",
            chat_id="123",
            content="hello",
            metadata={"account_id": account_id, "external_message_id": "message-1"},
        )
    )

    assert duplicate.metadata["conversation_duplicate"] is True


def test_channel_hub_resolves_account_control_actions_to_role_session(
    tmp_path: Path,
) -> None:
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    _ = service.create_role(
        role_id="mira",
        name="Mira",
        description="bound role",
        system_prompt="you are mira",
    )
    account_id = _live_account(service, "telegram")
    hub = ChannelHub(service)
    _ = hub.route_inbound(
        InboundMessage(
            channel="telegram",
            sender="u1",
            chat_id="123",
            content="hello",
            metadata={"account_id": account_id},
        )
    )

    assert hub.resolve_account_runtime_session_key(account_id) == "role:mira"
    with pytest.raises(PermissionError):
        hub.resolve_runtime_session_key("telegram", "123")


def test_channel_hub_rejects_unbound_control_actions(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )

    with pytest.raises(PermissionError):
        ChannelHub(service).resolve_runtime_session_key("telegram", "123")


def test_channel_hub_attaches_complete_role_execution_context(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    _ = service.create_role(
        role_id="mira",
        name="Mira",
        description="bound role",
        system_prompt="you are mira",
    )
    account_id = _live_account(service, "telegram")

    routed = ChannelHub(service).route_inbound(
        InboundMessage(
            channel="telegram",
            sender="u1",
            chat_id="123",
            content="hello",
            metadata={"account_id": account_id, "external_message_id": "message-1"},
        )
    )

    assert routed.metadata["role_id"] == "mira"
    assert routed.session_key == "role:mira"
    assert routed.metadata["thread_id"] == "thread:mira:telegram:123"
    assert routed.metadata["role_config_version"]
    assert routed.metadata["request_id"] == "message-1"
    assert routed.metadata["delivery_key"]
    assert routed.metadata["role_work_kind"] == "passive_turn"


def _hub_with_bindings(
    tmp_path: Path, blocked: tuple[str, ...] = ("7", "Troll")
) -> tuple[ChannelHub, str]:
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
    )
    _ = service.create_role(role_id="mira", name="Mira", system_prompt="you are mira")
    rules = AccountResponseRules(blocked_sender_ids=blocked)
    return ChannelHub(service), _live_account(service, "telegram", rules)


def test_channel_hub_admits_any_sender_of_a_bound_private_chat(
    tmp_path: Path,
) -> None:
    # The private chat itself is the partner; no contact is configured (#398).
    hub, account_id = _hub_with_bindings(tmp_path)

    assert hub.is_sender_allowed(
        channel="telegram", chat_id="123", sender_id="u1", account_id=account_id
    )


def test_channel_hub_admits_group_members_except_blacklisted(tmp_path: Path) -> None:
    hub, account_id = _hub_with_bindings(tmp_path)

    assert hub.is_sender_allowed(
        channel="telegram", chat_id="-100", sender_id="8", account_id=account_id
    )
    assert not hub.is_sender_allowed(
        channel="telegram", chat_id="-100", sender_id="7", account_id=account_id
    )


def test_channel_hub_matches_blacklisted_alias_case_insensitively(
    tmp_path: Path,
) -> None:
    hub, account_id = _hub_with_bindings(tmp_path)

    assert not hub.is_sender_allowed(
        channel="telegram",
        chat_id="-100",
        sender_id="9",
        sender_alias="troll",
        account_id=account_id,
    )
    assert hub.is_sender_allowed(
        channel="telegram",
        chat_id="-100",
        sender_id="9",
        sender_alias="friend",
        account_id=account_id,
    )
    # IDs match exactly: a numeric ID never matches by case folding.
    assert hub.is_sender_allowed(
        channel="telegram", chat_id="-100", sender_id="troll", account_id=account_id
    )


def test_channel_hub_ignores_at_marker_on_blacklisted_aliases(
    tmp_path: Path,
) -> None:
    # Users type usernames as "@Troll"; the normalizer drops the "@".
    hub, account_id = _hub_with_bindings(tmp_path, blocked=("@Troll",))

    assert not hub.is_sender_allowed(
        channel="telegram",
        chat_id="-100",
        sender_id="9",
        sender_alias="troll",
        account_id=account_id,
    )
    assert not hub.is_sender_allowed(
        channel="telegram",
        chat_id="-100",
        sender_id="9",
        sender_alias="@TROLL",
        account_id=account_id,
    )
    assert hub.is_sender_allowed(
        channel="telegram",
        chat_id="-100",
        sender_id="9",
        sender_alias="friend",
        account_id=account_id,
    )


def test_channel_hub_rejects_senders_of_unbound_sessions(tmp_path: Path) -> None:
    hub, _ = _hub_with_bindings(tmp_path)

    assert not hub.is_sender_allowed(channel="telegram", chat_id="-200", sender_id="8")


def test_channel_hub_blocks_only_blacklisted_senders_of_bound_sessions(
    tmp_path: Path,
) -> None:
    # Only /chatid asks this: an unbound session blocks nobody.
    hub, _ = _hub_with_bindings(tmp_path)

    assert not hub.is_sender_blocked(channel="telegram", chat_id="-100", sender_id="7")
    assert not hub.is_sender_blocked(
        channel="telegram", chat_id="-100", sender_id="9", sender_alias="troll"
    )
    assert not hub.is_sender_blocked(channel="telegram", chat_id="-100", sender_id="8")
    assert not hub.is_sender_blocked(channel="telegram", chat_id="-200", sender_id="7")


def _via(platform_account_id: str = "self") -> dict[str, str]:
    return {
        "platform": "telegram",
        "platform_account_id": platform_account_id,
        "display_name": "Mira Bot",
        "prefix": "Telegram 机器人「Mira Bot」（@mira_bot）",
    }


@pytest.mark.asyncio
async def test_plugin_snapshots_are_stored_as_given_and_outlive_the_account(
    tmp_path: Path,
) -> None:
    from core.accounts import AccountDeletionPlan
    from core.common.message_source import MessageSource

    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    service.create_role(
        role_id="mira", name="Mira", description="bound role", system_prompt="mira"
    )
    account_id = _live_account(service, "telegram")
    hub = ChannelHub(service)
    inbound = InboundMessage(
        channel="telegram",
        sender="u1",
        chat_id="123",
        content="hello",
        metadata={"account_id": account_id, "via_account": _via()},
    )
    routed = hub.route_inbound(inbound)
    assert routed.metadata["via_account"] == _via()
    # A snapshot naming another platform account is a plugin defect.
    with pytest.raises(ValueError, match="不一致"):
        hub.route_inbound(
            InboundMessage(
                channel="telegram",
                sender="u1",
                chat_id="123",
                content="hello",
                metadata={"account_id": account_id, "via_account": _via("other")},
            )
        )

    session = session_manager.get_or_create("role:mira")
    session.add_message("assistant", "reply", thread_id=routed.metadata["thread_id"])
    session_manager.save(session)
    committed = str(session.messages[-1]["id"])
    # A reply carries its trigger's routed metadata, sending account included.
    hub.mark_delivery(
        OutboundMessage(
            channel="telegram",
            chat_id="123",
            content="reply",
            metadata=dict(routed.metadata),
            committed_message_id=committed,
        ),
        default_channel="telegram",
        delivery_status="sent",
        external_message_id="tg-1",
        via_account=_via(),
    )
    assert session.messages[-1]["metadata"]["via_account"] == _via()

    async def done() -> None:
        return None

    accounts = service.repository.store.accounts
    accounts.set_delete_handler(
        "telegram", lambda ref: AccountDeletionPlan(disconnect=done, purge=done)
    )
    await accounts.delete(account_id, role_id="mira")

    stored = session_manager._store.get_message(committed)
    assert stored is not None
    assert stored["metadata"]["via_account"] == _via()
    source = MessageSource.from_metadata(stored["metadata"], session_key="role:mira")
    assert source.via_account == "Telegram 机器人「Mira Bot」（@mira_bot）"


@pytest.mark.parametrize(
    "via", [_via("other"), {"platform": "telegram", "prefix": "no account id"}]
)
def test_invalid_reply_snapshot_still_marks_the_sent_reply(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, via: dict[str, str]
) -> None:
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    service.create_role(
        role_id="mira", name="Mira", description="bound role", system_prompt="mira"
    )
    account_id = _live_account(service, "telegram")
    hub = ChannelHub(service)
    routed = hub.route_inbound(
        InboundMessage(
            channel="telegram",
            sender="u1",
            chat_id="123",
            content="hello",
            metadata={"account_id": account_id},
        )
    )
    session = session_manager.get_or_create("role:mira")
    session.add_message("assistant", "reply", thread_id=routed.metadata["thread_id"])
    session_manager.save(session)
    committed = str(session.messages[-1]["id"])

    with caplog.at_level("ERROR"):
        hub.mark_delivery(
            OutboundMessage(
                channel="telegram",
                chat_id="123",
                content="reply",
                metadata=dict(routed.metadata),
                committed_message_id=committed,
            ),
            default_channel="telegram",
            delivery_status="sent",
            external_message_id="tg-1",
            via_account=via,
        )

    # The reply was sent: it is marked so, only without the plugin's snapshot.
    stored = session_manager._store.get_message(committed)
    assert stored is not None
    assert (stored["delivery_status"], stored["external_message_id"]) == (
        "sent",
        "tg-1",
    )
    assert "via_account" not in (stored.get("metadata") or {})
    [record] = caplog.records
    assert record.levelname == "ERROR"
    assert account_id in record.getMessage()


def _hub_with_qq_account(
    tmp_path: Path, rules: AccountResponseRules | None = None
) -> tuple[ChannelHub, RoleStore, str]:
    store = RoleStore(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path, role_store=store, session_manager=SessionManager(tmp_path)
    )
    service.create_role(role_id="mira", name="Mira", system_prompt="mira")
    return ChannelHub(service), store, _live_account(service, "qq", rules)


def _private(account_id: str, content: str, **metadata: object) -> InboundMessage:
    return InboundMessage(
        channel="qq",
        sender="902",
        chat_id="902",
        content=content,
        metadata={"account_id": account_id, "chat_type": "private", **metadata},
    )


def test_pairing_code_binds_the_sender_and_marks_their_messages(
    tmp_path: Path,
) -> None:
    hub, store, account_id = _hub_with_qq_account(tmp_path)
    code = store.identities.create_pairing_code().code

    assert not hub.claim_pairing(_private(account_id, "hello"), scope="platform")
    before = hub.route_account_inbound(_private(account_id, "hello"))
    assert before is not None and "sender_is_user" not in before.metadata

    assert hub.claim_pairing(_private(account_id, code), scope="platform")
    [identity] = store.identities.list()
    assert (identity.plugin_id, identity.user_id, identity.scope) == (
        "qq",
        "902",
        "platform",
    )
    assert [(chat.channel, chat.chat_id) for chat in identity.chats] == [("qq", "902")]
    routed = hub.route_account_inbound(_private(account_id, "hello"))
    assert routed is not None and routed.metadata["sender_is_user"] is True

    store.identities.unbind(identity.id)
    after = hub.route_account_inbound(_private(account_id, "hello"))
    assert after is not None and "sender_is_user" not in after.metadata


def test_plugins_cannot_claim_the_user_flag(tmp_path: Path) -> None:
    hub, _, account_id = _hub_with_qq_account(tmp_path)

    routed = hub.route_account_inbound(
        _private(account_id, "hello", sender_is_user=True)
    )

    assert routed is not None and "sender_is_user" not in routed.metadata


def test_pairing_needs_a_live_owned_receiving_account(tmp_path: Path) -> None:
    hub, store, account_id = _hub_with_qq_account(tmp_path)
    code = store.identities.create_pairing_code().code
    store.accounts.report(account_id, "live", connection="offline")

    assert not hub.claim_pairing(_private(account_id, code), scope="platform")
    assert store.identities.list() == []


def test_blocklisted_sender_cannot_pair(tmp_path: Path) -> None:
    rules = AccountResponseRules(blocked_sender_ids=("902",))
    hub, store, account_id = _hub_with_qq_account(tmp_path, rules)
    code = store.identities.create_pairing_code().code

    assert not hub.claim_pairing(_private(account_id, code), scope="platform")
    # Routed as a normal message instead, which the blocklist drops.
    assert hub.route_account_inbound(_private(account_id, code)) is None
    assert store.identities.list() == []


def test_private_replies_off_still_allow_pairing(tmp_path: Path) -> None:
    rules = AccountResponseRules(private_enabled=False)
    hub, store, account_id = _hub_with_qq_account(tmp_path, rules)
    code = store.identities.create_pairing_code().code

    assert hub.claim_pairing(_private(account_id, code), scope="platform")
    [identity] = store.identities.list()
    assert identity.user_id == "902"


def _contact_name(hub: ChannelHub, thread_id: str) -> str:
    thread = hub._conversation.get_thread(thread_id)
    assert thread is not None
    contact = hub._conversation._store.get_contact(thread.contact_id)
    assert contact is not None
    return contact.display_name


def test_contacts_are_named_by_the_latest_group_or_sender_name(
    tmp_path: Path,
) -> None:
    hub, _, account_id = _hub_with_qq_account(tmp_path)

    def group(**names: object) -> InboundMessage:
        return InboundMessage(
            channel="qq",
            sender="902",
            chat_id="gqq:777",
            content="hello",
            metadata={
                "account_id": account_id,
                "chat_type": "group",
                "mentioned": True,
                "sender_name": "小明",
                **names,
            },
        )

    hub.route_account_inbound(group())
    assert _contact_name(hub, "thread:mira:qq:gqq:777") == "gqq:777"
    first = hub.route_account_inbound(
        group(group_name=" 读书会 ", external_message_id="m1")
    )
    assert _contact_name(hub, "thread:mira:qq:gqq:777") == "读书会"
    # A replayed message that is already archived does not rename the contact.
    assert first is not None
    sessions = hub._service.sessions._session_manager
    session = sessions.get_or_create(first.session_key)
    session.add_message(
        "user",
        "hello",
        thread_id=str(first.metadata["thread_id"]),
        external_message_id="m1",
    )
    sessions.save(session)
    replay = hub.route_account_inbound(
        group(group_name="重投的群名", external_message_id="m1")
    )
    assert replay is not None and replay.metadata["conversation_duplicate"] is True
    assert _contact_name(hub, "thread:mira:qq:gqq:777") == "读书会"
    # A message whose group name could not be fetched keeps the known name.
    hub.route_account_inbound(group())
    hub.route_account_inbound(group(group_name="  "))
    assert _contact_name(hub, "thread:mira:qq:gqq:777") == "读书会"
    hub.route_account_inbound(group(group_name="新读书会"))
    assert _contact_name(hub, "thread:mira:qq:gqq:777") == "新读书会"

    hub.route_account_inbound(_private(account_id, "hello", sender_name="小明"))
    assert _contact_name(hub, "thread:mira:qq:902") == "小明"
