"""The channel plugin capabilities: ``channels`` and ``avatars`` (#901 P2).

``PluginChannels`` is the ``host.channels`` core service: it keeps each plugin's
contributed transports and hands the channel host those of the active plugins,
in the order the plugin kernel gives (dependency depth, then id).
``PluginAvatars`` is the ``host.avatars`` core service over the shared cache of
channel senders' and chats' platform avatars (#514).
"""

from __future__ import annotations

import asyncio
import logging

from shiori_sdk.channels import Channel
from shiori_sdk.channels.avatars import AvatarFetch

from agent.plugin_host import PluginKernel
from agent.plugin_host.capabilities import ContributionsByPlugin, contribute_to_list
from agent.plugin_host.core_keys import (
    HOST_CHANNELS,
    PluginBinding,
    required_core_key,
)
from agent.plugin_host.diagnostics import ChannelDeclarationError
from agent.plugin_host.manifest import matches_channel_instance
from core.channel_avatars import AvatarKey, ChannelAvatarStore

logger = logging.getLogger(__name__)


class PluginChannels(ContributionsByPlugin[Channel]):
    """The ``host.channels`` core service of one plugin kernel generation."""

    def for_plugin(self, binding: PluginBinding) -> ChannelsCapability:
        """The channels capability of the plugin ``binding`` describes."""
        return ChannelsCapability(self.of(binding.plugin_id), binding)


def active_plugin_channels(kernel: PluginKernel) -> list[Channel]:
    """The channels the generation's active plugins contributed, in kernel order.

    Read from the started kernel (``host.channels``), not a kernel forwarder.
    """
    channels = required_core_key(kernel.kernel.get, HOST_CHANNELS)
    return list(channels.active(kernel.active_plugin_ids))


class ChannelsCapability:
    """贡献渠道 adapter；渠道宿主接管其生命周期。

    接受 manifest 声明的基础渠道、受限实例前缀，或带账号 ID 的基础渠道实例。
    未声明的名字不能绕过渠道归属校验。
    """

    def __init__(self, channels: list[Channel], binding: PluginBinding) -> None:
        declarations = binding.manifest.channels
        self._channels = channels
        self._effects = binding.scope
        self._plugin_id = binding.plugin_id
        self._declared = frozenset(declaration.name for declaration in declarations)
        self._instance_prefixes = tuple(
            declaration.instance_prefix
            for declaration in declarations
            if declaration.instance_prefix
        )

    def add(self, channel: Channel) -> None:
        """Hands ``channel`` to the channel host until the plugin stops.

        Raises ``ChannelDeclarationError`` when its name is not a channel the
        manifest declares, an allowed instance prefix, or an account instance
        of a declared channel.
        """
        name = getattr(channel, "name", None)
        prefixed_instance = any(
            matches_channel_instance(name, prefix) for prefix in self._instance_prefixes
        )
        # Account instances keep the declared provider prefix while receiving
        # separate transport names. The trusted plugin registers account_id.
        account_instance = (
            isinstance(name, str)
            and isinstance(getattr(channel, "account_id", None), str)
            and bool(getattr(channel, "account_id"))
            and any(
                name.startswith(f"{base}:") and len(name) > len(base) + 1
                for base in self._declared
            )
        )
        if (
            name not in self._declared
            and not prefixed_instance
            and not account_instance
        ):
            raise ChannelDeclarationError(self._plugin_id, str(name), self._declared)
        contribute_to_list(
            self._channels,
            channel,
            effects=self._effects,
            label=f"channel:{getattr(channel, 'name', channel)}",
        )

    def group(self, name: str):
        """Construct the host lifecycle coordinator without transferring its implementation."""
        from infra.channels.account_group import AccountChannelGroup

        return AccountChannelGroup(name)


class PluginAvatars:
    """The ``host.avatars`` core service over one ``ChannelAvatarStore``."""

    def __init__(self, store: ChannelAvatarStore) -> None:
        self._store = store

    def for_plugin(self, binding: PluginBinding) -> AvatarsCapability:
        """The avatars capability of the plugin ``binding`` describes."""
        return AvatarsCapability(self._store, binding)


class AvatarsCapability:
    """插件作用域的头像缓存接口，唯一的方法是 ``refresh``。

    头像按 ``kind`` 区分：``"sender"`` 为「渠道 + 发送者 ID」（与成员档案同一标识），
    ``"chat"`` 为「渠道 + 会话 ID」（群为群头像，私聊为对方头像）。``channel`` 是
    消息的传输渠道名，即 ``InboundMessage.channel``。

    宿主负责过期判断（7 天）、图片校验、缩图与存储；插件只负责下载。插件卸载后
    ``refresh`` 拒绝调用，尚未完成的后台获取被取消。
    """

    def __init__(self, store: ChannelAvatarStore, binding: PluginBinding) -> None:
        self._store = store
        self._effects = binding.scope
        self._plugin_id = binding.plugin_id
        self._tasks: set[asyncio.Task[None]] = set()
        self._cancel_registered = False

    def refresh(
        self, kind: str, channel: str, subject_id: str, fetch: AvatarFetch
    ) -> asyncio.Task[None] | None:
        """需要时在后台获取并保存这份头像，不阻塞调用方（通常是入站消息投递）。

        没有缓存或上次尝试已超过 7 天时才获取，并立即记下本次尝试时间：并发的
        其它调用、以及这次失败后的重试，都要等到下次到期；未到期时返回 None。
        到期时启动后台任务：``fetch`` 返回字节则校验缩图后保存（PNG/JPEG/GIF/WebP，
        不超过 1 MiB），返回 None 则记录平台上没有头像、显示占位图标。获取或保存
        失败只记一条警告日志，本次保持占位。返回该任务，供调用方需要时等待。
        种类未知或渠道、ID 为空时抛 ``ValueError``。
        """
        key = AvatarKey.parse(kind, channel, subject_id)
        self._effects.ensure_active("avatars:refresh")
        if not self._store.claim(key, plugin_id=self._plugin_id):
            return None
        if not self._cancel_registered:
            _ = self._effects.effect(self._cancel_pending, "avatars:refresh")
            self._cancel_registered = True
        task = asyncio.create_task(
            self._refresh(key, fetch), name=f"plugin:{self._plugin_id}:avatar"
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _refresh(self, key: AvatarKey, fetch: AvatarFetch) -> None:
        try:
            image = await fetch()
            if image is None:
                self._store.mark_missing(key, plugin_id=self._plugin_id)
            else:
                # 解码、缩图与写文件是阻塞工作，放到线程里，不占用事件循环。
                await asyncio.to_thread(
                    self._store.save, key, image, plugin_id=self._plugin_id
                )
        # 边界：头像只用于展示，任何获取或保存失败都不能影响消息收发。
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "插件 %s 的头像获取失败 %s %s/%s: %s",
                self._plugin_id,
                key.kind,
                key.channel,
                key.subject_id,
                exc,
            )

    async def _cancel_pending(self) -> None:
        tasks = [task for task in self._tasks if not task.done()]
        for task in tasks:
            _ = task.cancel()
        if tasks:
            _ = await asyncio.gather(*tasks, return_exceptions=True)
