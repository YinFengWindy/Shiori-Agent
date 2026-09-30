"""ctx.avatars：渠道插件把发送者与群的平台头像交给宿主缓存（#514）。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from agent.plugin_host.effects import EffectScope
from core.channel_avatars import AvatarKey, ChannelAvatarStore

logger = logging.getLogger(__name__)

# 插件提供的头像下载：返回图片字节；平台上确实没有头像时返回 None。
AvatarFetch = Callable[[], Awaitable[bytes | None]]


class AvatarsCapability:
    """插件作用域的头像缓存接口，唯一的方法是 ``refresh``。

    头像按 ``kind`` 区分：``"sender"`` 为「渠道 + 发送者 ID」（与成员档案同一标识），
    ``"chat"`` 为「渠道 + 会话 ID」（群为群头像，私聊为对方头像）。``channel`` 是
    消息的传输渠道名，即 ``InboundMessage.channel``。

    宿主负责过期判断（7 天）、图片校验、缩图与存储；插件只负责下载。插件卸载后
    ``refresh`` 拒绝调用，尚未完成的后台获取被取消。
    """

    def __init__(
        self, store: ChannelAvatarStore, effects: EffectScope, plugin_id: str
    ) -> None:
        self._store = store
        self._effects = effects
        self._plugin_id = plugin_id
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
            self._effects.add("avatars:refresh", self._cancel_pending)
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
