"""Message-stream framing: control packets out, batched and zlib command packets in."""

import json
import struct
import zlib

import pytest

from plugins.desktop_pet.backend.bilibili_live_packets import (
    OP_AUTH,
    AuthReply,
    Command,
    LivePacketError,
    decode_frame,
    encode_packet,
)


def packet(operation: int, version: int, body: bytes) -> bytes:
    return struct.pack(">IHHII", 16 + len(body), 16, version, operation, 0) + body


def command(body: dict) -> bytes:
    return packet(5, 0, json.dumps(body).encode("utf-8"))


def test_auth_packet_matches_the_documented_layout():
    data = encode_packet(OP_AUTH, {"roomid": 1})
    assert struct.unpack(">IHHII", data[:16]) == (len(data), 16, 1, 7, 1)
    assert json.loads(data[16:]) == {"roomid": 1}


def test_zlib_batches_and_plain_commands_decode_in_order():
    inner = command({"cmd": "A"}) + command({"cmd": "B"})
    frame = (
        packet(8, 1, b'{"code":0}')
        + packet(3, 1, b"\x00\x00\x00\x01")
        + packet(5, 2, zlib.compress(inner))
        + command({"cmd": "C"})
    )
    assert decode_frame(frame) == [
        AuthReply(code=0),
        Command({"cmd": "A"}),
        Command({"cmd": "B"}),
        Command({"cmd": "C"}),
    ]


def test_unrequested_brotli_and_truncated_frames_are_protocol_errors():
    with pytest.raises(LivePacketError, match="压缩版本 3"):
        decode_frame(packet(5, 3, b"..."))
    with pytest.raises(LivePacketError, match="截断"):
        decode_frame(command({"cmd": "A"})[:-1])
