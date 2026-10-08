"""Bilibili live message-stream packets: framing, decompression and commands.

Format (bilibili-API-collect ``docs/live/message_stream.md``, blivedm
``clients/ws_base.py``; verified 2026-10 against a live room): every packet is
a 16-byte big-endian header ``total length (u32), header length (u16, 16),
protocol version (u16), operation (u32), sequence (u32)`` and a body. One
websocket frame may carry several packets back to back.

Operations used here: 2 heartbeat (up), 3 heartbeat reply (popularity), 5
commands, 7 auth (up), 8 auth reply ``{"code": 0}``. Command bodies are JSON
(version 0) or zlib-compressed packet sequences (version 2). The auth packet
asks for ``protover`` 2, so brotli (version 3) is never requested and is
rejected as a protocol error rather than decoded.
"""

from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass
from typing import Any

_HEADER = struct.Struct(">IHHII")
# Size of every packet header: length, header size, version, operation, sequence.
HEADER_SIZE = _HEADER.size

OP_HEARTBEAT = 2
OP_HEARTBEAT_REPLY = 3
OP_COMMAND = 5
OP_AUTH = 7
OP_AUTH_REPLY = 8

_VERSION_PLAIN = 0
_VERSION_CONTROL = 1
_VERSION_ZLIB = 2
# The protover sent in the auth packet: command bodies arrive zlib-compressed.
AUTH_PROTOVER = _VERSION_ZLIB


class LivePacketError(ValueError):
    """A frame that does not follow the message-stream format."""


@dataclass(frozen=True)
class AuthReply:
    """The server's answer to the auth packet; ``code`` 0 means accepted."""

    code: int


@dataclass(frozen=True)
class Command:
    """One decoded JSON command such as ``DANMU_MSG``."""

    body: dict[str, Any]


type StreamItem = AuthReply | Command


def encode_packet(operation: int, body: dict[str, Any]) -> bytes:
    """Encode an upstream control packet (auth or heartbeat) with a JSON body."""
    payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
    header = _HEADER.pack(
        HEADER_SIZE + len(payload), HEADER_SIZE, _VERSION_CONTROL, operation, 1
    )
    return header + payload


def decode_frame(frame: bytes) -> list[StreamItem]:
    """Decode every packet of one websocket frame; heartbeat replies are dropped."""
    items: list[StreamItem] = []
    offset = 0
    while offset < len(frame):
        if len(frame) - offset < HEADER_SIZE:
            raise LivePacketError("直播信息流包头不完整")
        length, header_size, version, operation, _ = _HEADER.unpack_from(frame, offset)
        if length < header_size or header_size < HEADER_SIZE:
            raise LivePacketError("直播信息流包长度无效")
        if offset + length > len(frame):
            raise LivePacketError("直播信息流包被截断")
        body = frame[offset + header_size : offset + length]
        offset += length
        if operation == OP_AUTH_REPLY:
            items.append(AuthReply(code=_auth_code(body)))
        elif operation == OP_COMMAND:
            items.extend(_decode_commands(version, body))
    return items


def _decode_commands(version: int, body: bytes) -> list[StreamItem]:
    if version == _VERSION_ZLIB:
        return decode_frame(zlib.decompress(body))
    if version == _VERSION_PLAIN:
        value = json.loads(body.decode("utf-8"))
        if not isinstance(value, dict):
            raise LivePacketError("直播信息流命令不是 JSON 对象")
        return [Command(body=value)]
    raise LivePacketError(f"直播信息流使用了未请求的压缩版本 {version}")


def _auth_code(body: bytes) -> int:
    value = json.loads(body.decode("utf-8"))
    code = value.get("code") if isinstance(value, dict) else None
    if not isinstance(code, int):
        raise LivePacketError("直播信息流认证回复缺少 code")
    return code
