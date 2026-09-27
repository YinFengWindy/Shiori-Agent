"""Delete one Telegram Bot account: stop polling, purge caches, drop its Token."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.accounts import AccountDeletionPlan

if TYPE_CHECKING:
    from agent.plugin_host.kv import PluginKVStore

    from .channel.lifecycle import TelegramChannel

# Per-Bot KV caches written by the channel and account API.
_CACHE_PREFIXES = ("known_chats", "identity")


def config_without_bot(raw: dict[str, Any], ref: str) -> dict[str, Any] | None:
    """Returns the ``[plugins.telegram]`` table minus one Bot, or None if absent.

    Uses unexpanded values so other Bots' ``${ENV}`` Token references persist.
    The ``legacy`` Bot may still live in the old top-level ``token`` field.
    """
    bots = raw.get("bots") or []
    kept = [
        bot for bot in bots if not (isinstance(bot, dict) and bot.get("ref") == ref)
    ]
    legacy_token = ref == "legacy" and bool(raw.get("token"))
    if len(kept) == len(bots) and not legacy_token:
        return None
    return {**raw, "bots": kept, **({"token": ""} if legacy_token else {})}


class TelegramAccountDeletion:
    """The plugin's account delete hook over this generation's running Bots."""

    def __init__(
        self,
        channels: dict[str, TelegramChannel],
        store: PluginKVStore,
        raw_config: dict[str, Any],
    ) -> None:
        self._channels = channels
        self._store = store
        self._raw_config = raw_config

    def __call__(self, config_ref: str) -> AccountDeletionPlan:
        async def disconnect() -> None:
            channel = self._channels.pop(config_ref, None)
            if channel is not None:
                # Stopped before purging so polling cannot re-populate caches.
                await channel.retire()

        async def purge() -> None:
            for prefix in _CACHE_PREFIXES:
                self._store.delete(f"{prefix}:{config_ref}")

        return AccountDeletionPlan(
            disconnect=disconnect,
            purge=purge,
            plugin_config=config_without_bot(self._raw_config, config_ref),
        )
