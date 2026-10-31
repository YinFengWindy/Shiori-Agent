"""Private chats with the bound user that a role can reach through its accounts.

A role reaches the desktop user outside the desktop through the private chats
the user bound (``core.identity``) on one of the role's online accounts.
Proactive target selection lists these chats as candidates; initiated delivery
resolves a chosen one to the account that sends to it.
"""

from __future__ import annotations

from core.identity import IdentityChat, UserIdentity, identities_for_account
from core.roles.store import RoleStore
from shiori_sdk.accounts.models import AccountRecord
from shiori_sdk.accounts.targets import AccountTarget


def role_bound_chats(
    roles: RoleStore, role_id: str
) -> list[tuple[AccountRecord, UserIdentity, IdentityChat]]:
    """Private chats with the bound user through the role's online accounts.

    Ordered by binding, then by account within one binding.
    """
    records = [
        account.record
        for account in roles.accounts.list(role_id=role_id)
        if account.runtime_active and account.connection == "online"
    ]
    bindings = roles.identities.list()
    applicable = {
        record.id: identities_for_account(bindings, record) for record in records
    }
    return [
        (record, identity, chat)
        for identity in bindings
        for record in records
        if identity in applicable[record.id]
        and (chat := identity.chat_for(record.id)) is not None
    ]


def bound_chat_target(
    roles: RoleStore, role_id: str, channel: str, chat_id: str
) -> tuple[str, AccountTarget]:
    """The account channel and private target reaching a bound user's chat.

    The user is reached by their platform user ID through the role's account.
    Raises LookupError when ``channel`` / ``chat_id`` is not a bound chat of an
    online account of the role.
    """
    for record, identity, chat in role_bound_chats(roles, role_id):
        if (chat.channel, chat.chat_id) == (channel, chat_id):
            return record.plugin_id, AccountTarget("private", identity.user_id)
    raise LookupError(f"主动推送目标已不是绑定用户的私聊: {channel}:{chat_id}")
