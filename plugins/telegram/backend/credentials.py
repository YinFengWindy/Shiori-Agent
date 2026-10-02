"""Telegram Bot records in plugin storage and Token identity checks.

Each Bot the plugin serves is one record under the plugin KV key ``bots``::

    {"ref": "<[a-z0-9_]{1,48}>", "bot_id": "<numeric>", "token": "<token>",
     "enabled": true, "role_id": "<owner role>", "response_rules": {...}}

``token`` is the literal Bot Token or one whole ``${ENV_NAME}`` reference,
kept verbatim and only resolved when connecting. ``response_rules`` is the
``response_rules_to_dict`` form and absent until first edited. New Bots use
their ``bot_id`` as ``ref``, so a Bot deleted and added again keeps its
member channel ``telegram_<ref>`` and its history.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from telegram import Bot
from telegram.error import TelegramError

from collections.abc import Callable

if TYPE_CHECKING:
    from shiori_sdk.storage import KeyValueStore

BOTS_KEY = "bots"
# Per-Bot KV caches written by the channel and account API.
CACHE_PREFIXES = ("known_chats", "identity", "avatar")
_REF = re.compile(r"[a-z0-9_]{1,48}")
_ENV_REFERENCE = re.compile(r"^\$\{\w+\}$")


def bot_account_id(token: str) -> str:
    """The Bot's numeric platform ID, which a Bot Token starts with."""
    return token.split(":", 1)[0]


def avatar_key(ref: str) -> str:
    """The KV key holding one Bot's profile photo as a data URI ("" for none)."""
    return f"avatar:{ref}"


def resolve_token(token: str, resolver: Callable[[str], str]) -> str:
    """The usable Token behind a stored value; empty when its variable is unset."""
    resolved = resolver(token).strip()
    return "" if _ENV_REFERENCE.fullmatch(resolved) else resolved


def valid_ref(ref: str) -> bool:
    """Whether ``ref`` is a portable Bot reference (also its channel suffix)."""
    return _REF.fullmatch(ref) is not None


class TelegramBotStore:
    """The plugin's saved Bots; the only place their Tokens are kept."""

    def __init__(self, kv: KeyValueStore) -> None:
        self._kv = kv

    def list(self) -> list[dict[str, Any]]:
        rows = self._kv.get(BOTS_KEY, [])
        if not isinstance(rows, list):
            raise ValueError("Telegram Bot 数据格式错误")
        return rows

    def get(self, ref: str) -> dict[str, Any]:
        row = next((row for row in self.list() if row.get("ref") == ref), None)
        if row is None:
            raise KeyError(f"Telegram Bot 不存在: {ref}")
        return row

    def save(self, row: dict[str, Any]) -> None:
        """Inserts or replaces one Bot record by ``ref``."""
        rows = [item for item in self.list() if item.get("ref") != row["ref"]]
        self._kv.set(BOTS_KEY, [*rows, row])

    def remove(self, ref: str) -> None:
        """Deletes one Bot's record, Token and caches; idempotent."""
        rows = self.list()
        kept = [row for row in rows if row.get("ref") != ref]
        if len(kept) != len(rows):
            self._kv.set(BOTS_KEY, kept)
        for prefix in CACHE_PREFIXES:
            self._kv.delete(f"{prefix}:{ref}")


async def verify_bot_token(
    payload: dict[str, Any], resolver: Callable[[str], str]
) -> dict[str, object]:
    """Return the authenticated Bot identity without echoing its credential."""
    token = resolve_token(str(payload.get("token") or "").strip(), resolver)
    if not token:
        raise ValueError("Bot Token is required")
    try:
        async with Bot(token) as bot:
            identity = await bot.get_me()
    except (TelegramError, ValueError) as exc:
        raise ValueError("Bot Token 验证失败；请检查凭据和网络连接") from exc
    return {
        "bot_id": str(identity.id),
        "name": identity.full_name,
        "username": identity.username or "",
    }
