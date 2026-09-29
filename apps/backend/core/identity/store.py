"""Persistent store of the desktop user's bound platform identities."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from core.accounts import AccountRecord
from infra.persistence.json_store import atomic_save_json, load_json

from .models import IdentityChat, IdentityScope, UserIdentity, match_identity
from .pairing import PairingCode, PairingCodes

logger = logging.getLogger(__name__)

IDENTITIES_FILE = "user_identities.json"
_VERSION = 1

# Called after a binding was added, removed or changed; must not block, since
# it runs inside the channel intake or bridge call that made the change.
IdentityChangeListener = Callable[[], None]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UserIdentityStore:
    """Owns the user's bindings (``<workspace>/user_identities.json``) and pairing.

    The file is read on every query, so separate instances over one workspace
    always agree; writes are atomic. Pairing codes live only in this instance's
    memory, so the instance that issues them must be the one channel intake
    consumes them through (the runtime's shared ``RoleStore.identities``).
    """

    def __init__(
        self, workspace: Path, *, clock: Callable[[], datetime] = _now
    ) -> None:
        self._path = workspace / IDENTITIES_FILE
        self._clock = clock
        self._lock = RLock()
        self._pairing = PairingCodes(clock)
        self._listeners: list[IdentityChangeListener] = []

    def add_change_listener(self, listener: IdentityChangeListener) -> None:
        """Subscribes to binding changes (bind, unbind, a newly known chat)."""
        self._listeners.append(listener)

    def remove_change_listener(self, listener: IdentityChangeListener) -> None:
        """Withdraws a listener added with ``add_change_listener``."""
        self._listeners = [known for known in self._listeners if known != listener]

    def list(self) -> list[UserIdentity]:
        """All bindings, oldest first."""
        with self._lock:
            return self._read()

    def match(self, record: AccountRecord, user_id: str) -> UserIdentity | None:
        """The binding recognising ``user_id`` on messages of account ``record``."""
        return match_identity(self.list(), record, user_id)

    def create_pairing_code(self) -> PairingCode:
        """Issues the one-time code the user sends to bind an identity."""
        return self._pairing.create()

    def pair(
        self,
        text: str,
        *,
        record: AccountRecord,
        user_id: str,
        scope: IdentityScope,
        chat: IdentityChat,
    ) -> UserIdentity | None:
        """Binds ``user_id`` when ``text`` is the pending, unexpired pairing code.

        ``record`` is the account the code arrived through and ``chat`` the
        private chat it was sent in. Pairing an identity that is already bound
        keeps the binding, records the chat and refreshes ``bound_at``, so the
        desktop sees the code was used. Returns None, binding nothing, for any
        other text. The bindings file is read before the code is consumed, so
        a malformed file raises without using up the code.
        """
        if not user_id.strip():
            raise ValueError("平台用户 ID 不能为空")
        if chat.account_id != record.id:
            raise ValueError("配对私聊必须属于接收账号")
        with self._lock:
            identities = self._read()
            if not self._pairing.consume(text):
                return None
            bound_at = self._clock().isoformat()
            account_id = record.id if scope == "account" else ""
            existing = next(
                (
                    item
                    for item in identities
                    if (item.plugin_id, item.user_id, item.scope, item.account_id)
                    == (record.plugin_id, user_id, scope, account_id)
                ),
                None,
            )
            identity = (
                replace(existing, bound_at=bound_at)
                if existing is not None
                else UserIdentity(
                    id=uuid4().hex,
                    plugin_id=record.plugin_id,
                    user_id=user_id,
                    scope=scope,
                    account_id=account_id,
                    bound_at=bound_at,
                )
            )
            identity = _with_chat(identity, chat)
            self._write(
                [identity if item is existing else item for item in identities]
                if existing is not None
                else [*identities, identity]
            )
        logger.info(
            "[identity] 已绑定 plugin=%s user=%s scope=%s",
            record.plugin_id,
            user_id,
            scope,
        )
        self._notify()
        return identity

    def remember_chat(self, identity_id: str, chat: IdentityChat) -> None:
        """Records a private chat with a bound user; a known chat changes nothing."""
        with self._lock:
            identities = self._read()
            current = next(
                (item for item in identities if item.id == identity_id), None
            )
            if current is None or chat in current.chats:
                return
            updated = _with_chat(current, chat)
            self._write([updated if item is current else item for item in identities])
        self._notify()

    def forget_account(self, account_id: str) -> None:
        """Drops what binds the user to a deleted account.

        Bindings scoped to the account are removed and the account's private
        chats leave every other binding, so re-adding the account needs a new
        pairing before it is recognised or reached there.
        """
        with self._lock:
            identities = self._read()
            remaining = [
                replace(
                    item,
                    chats=tuple(
                        chat for chat in item.chats if chat.account_id != account_id
                    ),
                )
                for item in identities
                if not (item.scope == "account" and item.account_id == account_id)
            ]
            if remaining == identities:
                return
            self._write(remaining)
        self._notify()

    def unbind(self, identity_id: str) -> None:
        """Removes one binding; raises KeyError when it does not exist."""
        with self._lock:
            identities = self._read()
            remaining = [item for item in identities if item.id != identity_id]
            if len(remaining) == len(identities):
                raise KeyError(f"身份绑定不存在: {identity_id}")
            self._write(remaining)
        self._notify()

    def _read(self) -> list[UserIdentity]:
        payload = load_json(self._path, {"version": _VERSION, "identities": []})
        if not isinstance(payload, dict) or payload.get("version") != _VERSION:
            raise ValueError(f"身份绑定文件格式无效: {self._path}")
        rows = payload.get("identities")
        if not isinstance(rows, list):
            raise ValueError(f"身份绑定文件格式无效: {self._path}")
        return [UserIdentity.from_dict(row) for row in rows]

    def _write(self, identities: list[UserIdentity]) -> None:
        atomic_save_json(
            self._path,
            {
                "version": _VERSION,
                "identities": [item.to_dict() for item in identities],
            },
            domain="identity",
        )

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()


def _with_chat(identity: UserIdentity, chat: IdentityChat) -> UserIdentity:
    """The identity with ``chat`` as its only known chat on that account."""
    if chat in identity.chats:
        return identity
    others = tuple(
        item for item in identity.chats if item.account_id != chat.account_id
    )
    return replace(identity, chats=(*others, chat))
