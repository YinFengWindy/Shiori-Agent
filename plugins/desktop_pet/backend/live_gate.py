"""Preconditions of starting a live run (#292): pet role, room, TTS, login."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from shiori_sdk.roles import Roles

from .bilibili_credentials import BilibiliCredentials
from .live_config import LiveConfig, LiveConfigStore
from .voice_preferences import VoicePreferencesStore


class LiveStartGate:
    """Checks a role can start; each failure raises with a Chinese reason."""

    def __init__(
        self,
        *,
        roles: Roles,
        configs: LiveConfigStore,
        voice: VoicePreferencesStore,
        is_pet_role: Callable[[str], bool],
        credentials: Callable[[str], Awaitable[BilibiliCredentials]],
    ) -> None:
        self._roles = roles
        self._configs = configs
        self._voice = voice
        self._is_pet_role = is_pet_role
        self._credentials = credentials

    def require_role(self, role_id: str) -> None:
        """Reject an unknown role id."""
        if not role_id or self._roles.get_role(role_id) is None:
            raise ValueError("桌宠角色不存在")

    def require_pet_role(self, role_id: str) -> None:
        """The role must exist and be the pet's enabled role."""
        self.require_role(role_id)
        if not self._is_pet_role(role_id):
            raise ValueError("该角色未启用桌宠，无法开始直播互动")

    async def check(self, role_id: str) -> LiveConfig:
        """Every precondition; returns the settings to start with.

        The login is validated with Bilibili last, and raises
        ``BilibiliLoginRequired`` when missing or rejected.
        """
        self.require_pet_role(role_id)
        config = self._configs.read(role_id)
        if config.room_id is None:
            raise ValueError("尚未配置直播间")
        if not self._voice.read().speech_on:
            raise ValueError("桌宠语音未开启或未选择 TTS 服务，无法开始直播互动")
        await self._credentials(role_id)
        return config
