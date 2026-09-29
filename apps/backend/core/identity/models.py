"""The desktop user's bound platform identities.

A binding records who the desktop user is on one channel plugin's platform, so
messages they send there are recognised as the user's. The channel plugin
declares how far a platform user ID reaches:

- ``platform``: the ID names the user across the whole platform (a QQ number,
  a Telegram user ID), so one binding applies to every account of the plugin.
- ``account``: the ID only means something to the account it was seen by (a
  Feishu open_id, a QQBot openid), so a binding applies to that account only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from core.accounts import AccountRecord

IdentityScope = Literal["platform", "account"]
IDENTITY_SCOPES: tuple[IdentityScope, ...] = ("platform", "account")


def parse_identity_scope(value: object) -> IdentityScope:
    """Returns ``value`` as an identity scope; raises ValueError otherwise."""
    for scope in IDENTITY_SCOPES:
        if value == scope:
            return scope
    raise ValueError(f"身份作用域必须是 {' / '.join(IDENTITY_SCOPES)} 之一")


def _text(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str):
        raise ValueError(f"身份绑定缺少文本字段 {name}")
    return value


@dataclass(frozen=True)
class IdentityChat:
    """A private chat with the bound user through one account.

    ``channel`` / ``chat_id`` are the transport names the account's plugin
    used for that chat, i.e. the chat's conversation thread.
    """

    account_id: str
    channel: str
    chat_id: str

    def to_dict(self) -> dict[str, str]:
        """The JSON form stored with the binding."""
        return {
            "account_id": self.account_id,
            "channel": self.channel,
            "chat_id": self.chat_id,
        }

    @classmethod
    def from_dict(cls, payload: object) -> IdentityChat:
        """Reads a stored chat; raises ValueError if malformed."""
        if not isinstance(payload, dict):
            raise ValueError("身份绑定的私聊记录必须是对象")
        chat = cls(
            _text(payload, "account_id"),
            _text(payload, "channel"),
            _text(payload, "chat_id"),
        )
        if not all((chat.account_id, chat.channel, chat.chat_id)):
            raise ValueError("身份绑定的私聊记录字段不能为空")
        return chat


@dataclass(frozen=True)
class UserIdentity:
    """One bound platform identity of the desktop user.

    ``account_id`` is the account an ``account``-scoped ID belongs to and is
    empty for ``platform`` scope. ``chats`` are the private chats with the
    user known so far (the one the pairing code came through, plus any the
    user later wrote in); they are where proactive messages can reach them.
    """

    id: str
    plugin_id: str
    user_id: str
    scope: IdentityScope
    account_id: str
    bound_at: str
    chats: tuple[IdentityChat, ...] = ()

    def applies_to(self, record: AccountRecord) -> bool:
        """Whether this identity is recognised on messages of ``record``."""
        return record.plugin_id == self.plugin_id and (
            self.scope == "platform" or record.id == self.account_id
        )

    def to_dict(self) -> dict[str, Any]:
        """The JSON form stored in the identity file."""
        return {
            "id": self.id,
            "plugin_id": self.plugin_id,
            "user_id": self.user_id,
            "scope": self.scope,
            "account_id": self.account_id,
            "bound_at": self.bound_at,
            "chats": [chat.to_dict() for chat in self.chats],
        }

    @classmethod
    def from_dict(cls, payload: object) -> UserIdentity:
        """Reads a stored binding; raises ValueError if malformed."""
        if not isinstance(payload, dict):
            raise ValueError("身份绑定必须是对象")
        chats = payload.get("chats")
        if not isinstance(chats, list):
            raise ValueError("身份绑定的私聊记录必须是数组")
        identity = cls(
            id=_text(payload, "id"),
            plugin_id=_text(payload, "plugin_id"),
            user_id=_text(payload, "user_id"),
            scope=parse_identity_scope(payload.get("scope")),
            account_id=_text(payload, "account_id"),
            bound_at=_text(payload, "bound_at"),
            chats=tuple(IdentityChat.from_dict(item) for item in chats),
        )
        if not all((identity.id, identity.plugin_id, identity.user_id)):
            raise ValueError("身份绑定的 ID、插件和平台用户 ID 不能为空")
        if (identity.scope == "account") != bool(identity.account_id):
            raise ValueError("只有按账号作用域的身份绑定带账号 ID")
        return identity
