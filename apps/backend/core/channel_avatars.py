"""渠道发送者与群的头像缓存（#514）。

- 发送者按「渠道 + 发送者 ID」识别，与成员档案的 ``MemberKey`` 一致；会话（群或
  私聊）按「渠道 + 会话 ID」识别。私聊会话的头像就是对方的头像。
- 插件持有平台凭证、负责下载图片；宿主负责过期判断、校验缩图与存储。头像缩成固定
  小尺寸 PNG 单独存文件（工作区 ``private_runtime/channel-avatars/``，按标识命名、
  覆盖更新），索引只记相对路径、最近一次尝试时间和插件 ID，不写进消息元数据或
  账号数据，所以缓存大小只随见过的发送者与会话数增长。
- 索引每次查询都读文件，同一工作区上的多个实例结论一致；写入是原子的。
"""

from __future__ import annotations

import io
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Literal

from core.common.media import write_png_thumbnail
from infra.persistence.json_store import atomic_save_json, load_json
from infra.persistence.keyed_names import keyed_file_name
from infra.persistence.text_store import atomic_save_bytes

# 头像多久重新获取一次：超过这个时间后，该发送者或会话下次有消息时再取。
AVATAR_TTL = timedelta(days=7)
# 缓存头像的边长上限（像素），小手机与身份列表的头像显示尺寸的两倍余量。
AVATAR_SIZE = 128
# 插件交来的原始图片字节上限；平台头像的小尺寸版本远小于此。
MAX_AVATAR_BYTES = 1024 * 1024
# 可接受的原始图片格式（Pillow 格式名）。
AVATAR_FORMATS = ("PNG", "JPEG", "GIF", "WEBP")
AVATARS_DIR = Path("private_runtime") / "channel-avatars"
_INDEX_FILE = "index.json"
_VERSION = 1

AvatarKind = Literal["sender", "chat"]
AVATAR_KINDS: tuple[AvatarKind, ...] = ("sender", "chat")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"头像标识缺少 {name}")
    return value.strip()


@dataclass(frozen=True)
class AvatarKey:
    """一份头像的标识：``sender`` 为「渠道 + 发送者 ID」，``chat`` 为「渠道 + 会话 ID」。"""

    kind: AvatarKind
    channel: str
    subject_id: str

    @classmethod
    def parse(cls, kind: object, channel: object, subject_id: object) -> AvatarKey:
        """校验插件传入的标识；种类未知或渠道、ID 为空时抛 ``ValueError``。"""
        for known in AVATAR_KINDS:
            if kind == known:
                return cls(known, _text(channel, "渠道"), _text(subject_id, "ID"))
        raise ValueError(f"头像种类必须是 {' / '.join(AVATAR_KINDS)} 之一")

    @property
    def file_name(self) -> str:
        """头像文件在其种类目录下的文件名。"""
        return keyed_file_name(f"{self.channel}:{self.subject_id}", ".png")


@dataclass(frozen=True)
class AvatarEntry:
    """索引里的一条：``file`` 是相对缓存目录的路径，空串表示平台上没有头像或尚未取到。"""

    plugin_id: str
    attempted_at: datetime
    file: str = ""


class AvatarIndex:
    """一次读取的头像索引，供桥接在一个请求里批量查询头像文件的绝对路径。"""

    def __init__(self, root: Path, entries: dict[AvatarKey, AvatarEntry]) -> None:
        self._root = root
        self._entries = entries

    def path(self, key: AvatarKey) -> str | None:
        """``key`` 的头像文件绝对路径；没有缓存、平台上没有头像或文件已不在时为 None。"""
        entry = self._entries.get(key)
        if entry is None or not entry.file:
            return None
        path = self._root / entry.file
        return str(path) if path.is_file() else None

    def sender(self, channel: str | None, sender_id: str | None) -> str | None:
        """发送者头像；渠道或发送者未知时为 None。"""
        if not channel or not sender_id:
            return None
        return self.path(AvatarKey("sender", channel, sender_id))

    def chat(self, channel: str | None, chat_id: str | None) -> str | None:
        """会话头像：群为群头像，私聊为对方头像；渠道或会话未知时为 None。"""
        if not channel or not chat_id:
            return None
        return self.path(AvatarKey("chat", channel, chat_id))

    def sender_avatars(self, sender_id: str) -> list[tuple[str, str]]:
        """``sender_id`` 在各渠道已缓存的头像：``(渠道, 文件绝对路径)``，最近获取的在前。

        同一平台 ID 在不同渠道（如同一插件的多个账号实例）各有一份；由调用方按自己的
        规则决定哪些渠道算数。
        """
        found = [
            (entry.attempted_at, key.channel, path)
            for key, entry in self._entries.items()
            if key.kind == "sender"
            and key.subject_id == sender_id
            and (path := self.path(key)) is not None
        ]
        found.sort(reverse=True)
        return [(channel, path) for _, channel, path in found]


class ChannelAvatarStore:
    """头像缓存的唯一写入方：认领刷新、保存图片、记录无头像，并提供只读索引。"""

    def __init__(
        self, workspace: Path, *, clock: Callable[[], datetime] = _now
    ) -> None:
        self.root = workspace / AVATARS_DIR
        self._index_path = self.root / _INDEX_FILE
        self._clock = clock
        self._lock = RLock()

    def index(self) -> AvatarIndex:
        """当前索引的一次读取。"""
        with self._lock:
            return AvatarIndex(self.root, self._read())

    def claim(self, key: AvatarKey, *, plugin_id: str) -> bool:
        """``key`` 的头像是否该由调用方现在去获取。

        没有缓存，或最近一次尝试已超过 ``AVATAR_TTL`` 时返回 True，并把尝试时间记为
        现在：并发的第二次认领、以及这次获取失败后的重试都要等到下次到期。已有的头像
        文件在新图保存前保持不变。
        """
        with self._lock:
            entries = self._read()
            now = self._clock()
            entry = entries.get(key)
            if entry is not None and now - entry.attempted_at < AVATAR_TTL:
                return False
            entries[key] = AvatarEntry(
                plugin_id, now, entry.file if entry is not None else ""
            )
            self._write(entries)
            return True

    def save(self, key: AvatarKey, image: bytes, *, plugin_id: str) -> None:
        """校验 ``image`` 为图片、缩图后覆盖写入 ``key`` 的头像文件并记录。

        解码与缩图是阻塞的 CPU 工作，异步调用方应放到线程里执行。

        超过 ``MAX_AVATAR_BYTES``、不是 PNG/JPEG/GIF/WebP 或无法解码时抛
        ``ValueError``，原有缓存不变。
        """
        if len(image) > MAX_AVATAR_BYTES:
            raise ValueError("头像图片超过 1 MiB")
        thumbnail = io.BytesIO()
        write_png_thumbnail(image, thumbnail, AVATAR_SIZE, formats=AVATAR_FORMATS)
        relative = f"{key.kind}/{key.file_name}"
        target = self.root / relative
        with self._lock:
            entries = self._read()
            atomic_save_bytes(target, thumbnail.getvalue())
            entries[key] = AvatarEntry(plugin_id, self._clock(), relative)
            self._write(entries)

    def mark_missing(self, key: AvatarKey, *, plugin_id: str) -> None:
        """记录平台上没有 ``key`` 的头像：删除旧文件，显示回到占位图标，到期再查。"""
        with self._lock:
            entries = self._read()
            entry = entries.get(key)
            if entry is not None and entry.file:
                (self.root / entry.file).unlink(missing_ok=True)
            entries[key] = AvatarEntry(plugin_id, self._clock())
            self._write(entries)

    def _read(self) -> dict[AvatarKey, AvatarEntry]:
        payload = load_json(self._index_path, None, domain="channel_avatars")
        if payload is None:
            return {}
        if not isinstance(payload, dict) or payload.get("version") != _VERSION:
            raise ValueError(f"头像索引格式不符: {self._index_path}")
        rows = payload.get("avatars")
        if not isinstance(rows, list):
            raise ValueError(f"头像索引格式不符: {self._index_path}")
        return dict(_parse_row(row) for row in rows)

    def _write(self, entries: dict[AvatarKey, AvatarEntry]) -> None:
        atomic_save_json(
            self._index_path,
            {"version": _VERSION, "avatars": list(_rows(entries))},
            domain="channel_avatars",
        )


def _parse_row(row: object) -> tuple[AvatarKey, AvatarEntry]:
    if not isinstance(row, dict):
        raise ValueError("头像索引条目必须是对象")
    key = AvatarKey.parse(row.get("kind"), row.get("channel"), row.get("id"))
    file = row.get("file")
    if not isinstance(file, str):
        raise ValueError("头像索引条目缺少 file")
    entry = AvatarEntry(
        plugin_id=_text(row.get("plugin_id"), "插件 ID"),
        attempted_at=datetime.fromisoformat(_text(row.get("attempted_at"), "时间")),
        file=file,
    )
    return key, entry


def _rows(entries: dict[AvatarKey, AvatarEntry]) -> Iterable[dict[str, Any]]:
    for key, entry in entries.items():
        yield {
            "kind": key.kind,
            "channel": key.channel,
            "id": key.subject_id,
            "plugin_id": entry.plugin_id,
            "attempted_at": entry.attempted_at.isoformat(),
            "file": entry.file,
        }
