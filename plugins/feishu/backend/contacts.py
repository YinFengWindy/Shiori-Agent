"""Feishu senders' contact profiles: names cached by the plugin, avatars by the host.

A received message only carries the sender's open_id. The contact API answers
their name and avatar, given the app's ``contact:user.base:readonly``
permission. Both are fetched in the background with the host's avatar refresh
(``ctx.avatars``, every 7 days per sender), so delivery never waits on it: the
name reaches the messages after the fetch, the avatar the phone. Without the
permission the fetch fails, the host logs a warning and the sender keeps the
placeholder avatar and no name.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from bus.events import InboundMessage

from .api import FeishuApi
from .formatting import as_dict

if TYPE_CHECKING:
    from shiori_sdk.channels.avatars import AvatarsCapability
    from agent.plugin_host.kv import PluginKVStore


class FeishuContacts:
    """One application's view of its senders (open_ids are scoped to the app)."""

    def __init__(
        self,
        api: FeishuApi,
        *,
        store: PluginKVStore | None,
        ref: str,
        avatars: AvatarsCapability | None,
    ) -> None:
        self._api = api
        self._store = store
        self._key = f"contacts:{ref}"
        self._avatars = avatars

    def name(self, open_id: str) -> str | None:
        """The sender's name from the last contact fetch; None until one succeeded."""
        if self._store is None:
            return None
        names = self._store.get(self._key, {})
        name = names.get(open_id) if isinstance(names, dict) else None
        return name if isinstance(name, str) and name else None

    def refresh(self, message: InboundMessage) -> None:
        """Asks the host to refresh the sender's avatar and, with it, their name.

        A private chat's avatar is the sender's: when both keys are due, one
        contact lookup and download serves both. The host runs the fetch in the
        background, only when due.
        """
        if self._avatars is None:
            return
        open_id = message.sender
        shared: asyncio.Task[bytes | None] | None = None

        def fetch() -> asyncio.Task[bytes | None]:
            # 首个到期的键启动获取，另一个键等待同一个任务。
            nonlocal shared
            if shared is None:
                shared = asyncio.ensure_future(self._fetch(open_id))
            return shared

        _ = self._avatars.refresh("sender", message.channel, open_id, fetch)
        _ = self._avatars.refresh("chat", message.channel, message.chat_id, fetch)

    async def _fetch(self, open_id: str) -> bytes | None:
        user = await self._api.get_user(open_id)
        name = str(user.get("name") or "").strip()
        if name:
            self._remember(open_id, name)
        avatar = as_dict(user.get("avatar"))
        url = str(avatar.get("avatar_240") or avatar.get("avatar_72") or "")
        return await self._api.fetch_url(url) if url else None

    def _remember(self, open_id: str, name: str) -> None:
        if self._store is None:
            return
        names = self._store.get(self._key, {})
        known = dict(names) if isinstance(names, dict) else {}
        if known.get(open_id) != name:
            known[open_id] = name
            self._store.set(self._key, known)
