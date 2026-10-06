from plugins.minimax_tts.backend.stream import parse_minimax_stream_chunks


def test_minimax_stream_parser_handles_split_sse_lines_and_hex_chunks() -> None:
    chunks = [
        b'data: {"data":{"audio":"0001"}}\n',
        b'data: {"data":{"audio":"ff"}}\n\n',
        b"data: [DONE]\n",
    ]

    assert list(parse_minimax_stream_chunks(chunks)) == [b"\x00\x01", b"\xff"]
