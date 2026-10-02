"""Public host contract for communication account records and access fences.

Plugins own every account record (identity, owner role, response rules,
credentials) in their own storage; the host only keeps an in-memory index of
the accounts its loaded plugins registered.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import asdict, dataclass
from typing import Literal

logger = logging.getLogger(__name__)

ConnectionState = Literal[
    "unknown", "connecting", "online", "offline", "login_required", "error"
]


@dataclass(frozen=True)
class AccountResponseRules:
    """How an account responds; saved by its plugin, applied by host routing.

    Every group chat follows the same account-wide group settings; within an
    enabled group the role only speaks when @-mentioned or replied to.
    """

    private_enabled: bool = True
    group_enabled: bool = True
    blocked_sender_ids: tuple[str, ...] = ()


def account_id_for(plugin_id: str, platform_account_id: str) -> str:
    """The deterministic account ID: ``<plugin_id>:<platform_account_id>``.

    Derived from the identity alone, so deleting and re-adding the same
    platform account yields the same ID and its history stays attached.
    """
    return f"{plugin_id}:{platform_account_id}"


# Message metadata key of the ``ViaAccount`` snapshot a plugin supplies.
VIA_ACCOUNT_KEY = "via_account"


@dataclass(frozen=True)
class ViaAccount:
    """The account a message came in or went out through, as its plugin saw it.

    Channel plugins build it themselves and attach ``to_metadata()`` under
    ``VIA_ACCOUNT_KEY``: to inbound message metadata, to
    ``ChannelHub.mark_delivery(via_account=...)`` for replies, and to
    ``account.send`` results. The host stores it with the message as-is, so it
    stays readable after the account is deleted, and shows ``prefix`` to the
    model as the message's 「经由账号」.
    """

    platform: str
    platform_account_id: str
    # The account's display name when the message passed; may be empty.
    display_name: str
    # Plugin-formatted source text, e.g. how the platform names the account.
    prefix: str

    def to_metadata(self) -> dict[str, str]:
        """The JSON-safe form stored in message metadata."""
        return asdict(self)

    @classmethod
    def from_metadata(cls, value: object) -> ViaAccount:
        """Reads a stored or plugin-supplied snapshot; raises ValueError if malformed."""
        if not isinstance(value, dict):
            raise ValueError("经由账号快照必须是对象")
        fields: dict[str, str] = {}
        for name in ("platform", "platform_account_id", "display_name", "prefix"):
            item = value.get(name)
            if not isinstance(item, str):
                raise ValueError(f"经由账号快照缺少文本字段 {name}")
            fields[name] = item
        if not all(
            fields[name].strip()
            for name in ("platform", "platform_account_id", "prefix")
        ):
            raise ValueError("经由账号快照的平台、平台账号和前缀不能为空")
        return cls(**fields)

    @classmethod
    def for_account(cls, value: object, record: AccountRecord) -> ViaAccount:
        """Reads a plugin snapshot that must describe ``record``'s platform account."""
        via = cls.from_metadata(value)
        if (via.platform, via.platform_account_id) != (
            record.platform,
            record.platform_account_id,
        ):
            raise ValueError("经由账号快照与账号不一致")
        return via


def delivered_via_account(
    value: object, record: AccountRecord
) -> dict[str, str] | None:
    """The snapshot to store with a message ``record``'s account already sent.

    Checked like every snapshot (``ViaAccount.for_account``), but the platform
    has accepted the message, so a malformed or mismatched snapshot (a plugin
    contract violation) must not undo recording the send: it is logged as an
    error and the message is stored without one. None when there is no
    snapshot to store.
    """
    if value is None:
        return None
    try:
        return ViaAccount.for_account(value, record).to_metadata()
    except ValueError as exc:
        logger.error(
            "插件 %s 为账号 %s 提供的经由账号快照无效，消息不带快照记录: %s; 快照=%r",
            record.plugin_id,
            record.id,
            exc,
            value,
        )
        return None


@dataclass(frozen=True)
class AccountRecord:
    """One registered account; config_ref names plugin-private data, never a secret."""

    id: str
    plugin_id: str
    platform: str
    platform_account_id: str
    config_ref: str
    role_id: str
    display_name: str = ""
    # The platform account's own picture as an image ``data:`` URI (checked
    # by ``AccountRegistry.register``); empty when unknown.
    avatar_url: str = ""
    response_rules: AccountResponseRules = AccountResponseRules()


def account_serves_channel(record: AccountRecord, channel: str) -> bool:
    """Whether transport ``channel`` can carry messages of account ``record``.

    A plugin names its channel after the platform, either plainly (``qq``) or
    per account instance (``telegram_<ref>``, ``feishu:<ref>``). The rule
    matches on the platform alone; a role holds at most one account per
    plugin, so among one role's accounts it picks out a single account.
    """
    platform = record.platform
    return (
        channel == platform
        or channel.startswith(f"{platform}:")
        or channel.startswith(f"{platform}_")
    )


def account_for_channel(
    records: Iterable[AccountRecord], channel: str
) -> AccountRecord | None:
    """The account among one role's ``records`` carrying transport ``channel``.

    A role holds at most one account per plugin, so ``account_serves_channel``
    picks out at most one; None when the role has no account there.
    """
    return next(
        (record for record in records if account_serves_channel(record, channel)),
        None,
    )


@dataclass(frozen=True)
class AccountSnapshot:
    """One authoritative view shared by role scheduling and presentation."""

    record: AccountRecord
    runtime_active: bool
    connection: ConnectionState
    capabilities: frozenset[str]
    error: str = ""


@dataclass(frozen=True)
class AccountAccess:
    """Ownership fence captured before an account operation starts."""

    account_id: str
    role_id: str
    runtime_token: str


class AccountNotFoundError(KeyError):
    """No loaded plugin has registered the requested account."""


class AccountDeletingError(RuntimeError):
    """The account is being deleted; its identity and settings are frozen."""


@dataclass(frozen=True)
class AccountDeletionPlan:
    """A plugin's side-effect-free plan for deleting one of its accounts.

    The host runs ``disconnect`` then ``purge``, then drops the account from
    its index. Both steps must be idempotent, and planning must still work
    after a purge, so a failed deletion can simply be retried.
    """

    # Stops the connection and all reports for the account; keeps its data.
    disconnect: Callable[[], Awaitable[None]]
    # Deletes the plugin's record, credentials, caches, and private files.
    purge: Callable[[], Awaitable[None]]


# A plugin delete hook receives the account's plugin-private config_ref and
# returns its plan without side effects; raising aborts before anything changes.
AccountDeleteHandler = Callable[[str], AccountDeletionPlan]

# A plugin rules hook durably saves new response rules for the account behind
# ``config_ref`` in the plugin's own storage; raising leaves the rules unchanged.
AccountRulesHandler = Callable[[str, AccountResponseRules], None]
